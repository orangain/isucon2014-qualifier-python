# coding: utf-8

import os
import hashlib
from datetime import datetime
import json

import redis
from bottle import Bottle, request, response, redirect, run
from werkzeug.contrib.fixers import ProxyFix

from views import render_index, render_mypage


config = {}
app = Bottle()


class Top(object):
    redis = None

top = Top()
PASSWORDS = {}
BANNED_IPS = set()
LOCKED_USERS = set()


def load_config():
    global config
    config = {
        'user_lock_threshold': int(os.environ.get('ISU4_USER_LOCK_THRESHOLD', 3)),
        'ip_ban_threshold': int(os.environ.get('ISU4_IP_BAN_THRESHOLD', 10))
    }
    return config


def init_data():
    global PASSWORDS, BANNED_IPS, LOCKED_USERS
    PASSWORDS = {}
    BANNED_IPS = set()
    LOCKED_USERS = set()

    for id, login, password, salt, password_hash in load_users():
        PASSWORDS[login] = password

    # There is no banned ip at the initial time
    with open('/home/isucon/sql/dummy_users_used.tsv') as f:
        for line in f:
            id, login, failure = line.rstrip().split('\t')
            if int(failure) >= config['user_lock_threshold']:
                user_key = _user_key(login)
                LOCKED_USERS.add(user_key)


def connect_redis():
    #r = redis.StrictRedis(host='localhost', port=6379, db=0)
    r = redis.StrictRedis(unix_socket_path='/tmp/redis.sock', db=0)
    return r


def get_redis():
    if top.redis is None:
        top.redis = connect_redis()
    return top.redis


def calculate_password_hash(password, salt):
    return hashlib.sha256(password + ':' + salt).hexdigest()


def _user_key(user_login):
    return 'U:{0}'.format(user_login)


def _login_key(user_login):
    return 'L:{0}'.format(user_login)


def _ip_key(ip):
    return 'IP:{0}'.format(ip)


def load_data():
    def connect_db():
        import MySQLdb
        from MySQLdb.cursors import DictCursor

        host = os.environ.get('ISU4_DB_HOST', 'localhost')
        port = int(os.environ.get('ISU4_DB_PORT', '3306'))
        dbname = os.environ.get('ISU4_DB_NAME', 'isu4_qualifier')
        username = os.environ.get('ISU4_DB_USER', 'root')
        password = os.environ.get('ISU4_DB_PASSWORD', '')
        db = MySQLdb.connect(host=host, port=port, db=dbname, user=username,
                             passwd=password, cursorclass=DictCursor, charset='utf8')
        return db

    def login_log(succeeded, login, user_id=None, ip=None, now=None, r=None):
        if r is None:
            r = get_redis()
        if ip is None:
            ip = request.remote_addr
        if now is None:
            now = datetime.now()

        user_key = _user_key(login)
        login_key = _login_key(login)
        ip_key = _ip_key(ip)
        #print('login_log: ' + str(succeeded) + ', ' + login + ', ' + str(user_id) + ', ' + ip)
        if succeeded:
            pipe = r.pipeline()
            pipe.set(user_key, 0)
            pipe.hset(login_key, 'last_login_at', now.strftime("%Y-%m-%d %H:%M:%S"))
            pipe.hset(login_key, 'last_login_ip', ip)
            pipe.set(ip_key, 0)
            pipe.execute()
        elif user_id:
            pipe = r.pipeline()
            pipe.incr(user_key)
            pipe.incr(ip_key)
            pipe.execute()
        else:
            r.incr(ip_key)

    r = connect_redis()
    r.flushall()

    for id, login, password, salt, password_hash in load_users():
        user_key = _user_key(login)
        r.set(user_key, 0)

    cur = connect_db().cursor()
    cur.execute('SELECT * FROM login_log')
    for row in cur.fetchall():
        login_log(bool(row['succeeded']), row['login'], row['user_id'],
                  row['ip'], row['created_at'], r)

    cur.close()


def load_users():
    with open('/home/isucon/sql/dummy_users.tsv') as f:
        for line in f:
            id, login, password, salt, password_hash = line.rstrip().split('\t')
            yield id, login, password, salt, password_hash


def user_locked(user_key, failures):
    if user_key in LOCKED_USERS:
        return True

    locked = int(failures or 0) >= config['user_lock_threshold']
    if locked:
        LOCKED_USERS.add(user_key)

    return locked


def ip_banned(ip_key, failures):
    banned = int(failures or 0) >= config['ip_ban_threshold']
    if banned:
        BANNED_IPS.add(ip_key)

    return banned


def attempt_login(login, password):
    r = get_redis()
    user_key = _user_key(login)
    login_key = _login_key(login)
    user_password = PASSWORDS.get(login)
    ip = request.remote_addr
    ip_key = _ip_key(ip)

    if ip_key in BANNED_IPS:
        if user_password:
            r.incr(user_key)
        return [None, 'banned']

    read_pipe = r.pipeline()
    read_pipe.get(ip_key)
    read_pipe.get(user_key)
    read_pipe.hgetall(login_key)
    ip_failures, user_failures, user = read_pipe.execute()

    if ip_banned(ip_key, ip_failures):
        if user_password:
            r.incr(user_key)
        return [None, 'banned']

    if not user_password:
        r.incr(ip_key)
        return [None, 'wrong_login_or_password']

    # when user exists

    if user_locked(user_key, user_failures):
        r.incr(ip_key)
        return [None, 'locked']

    if user_password and password == user_password:
        response.set_cookie('login', login)
        response.set_cookie('last_login_at', str(user.get('last_login_at')).replace(' ', '+'))
        response.set_cookie('last_login_ip', str(user.get('last_login_ip')))

        write_pipe = r.pipeline()
        write_pipe.set(user_key, 0)
        write_pipe.hset(login_key, 'last_login_at', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        write_pipe.hset(login_key, 'last_login_ip', ip)
        write_pipe.set(ip_key, 0)
        write_pipe.execute()

        return [True, None]
    else:
        write_pipe = r.pipeline()
        write_pipe.incr(user_key)
        write_pipe.incr(ip_key)
        write_pipe.execute()

        return [None, 'wrong_login_or_password']


def get_ban_report(r=None):
    banned_ips = []
    locked_users = []

    if r is None:
        r = get_redis()

    for key in r.keys():
        if ':' not in key:
            continue
        key_type, key_id = key.split(':')

        if key_type == 'U':
            if int(r.get(key)) >= config['user_lock_threshold']:
                locked_users.append(key_id)
        elif key_type == 'IP':
            if int(r.get(key)) >= config['ip_ban_threshold']:
                banned_ips.append(key_id)

    return {'banned_ips': banned_ips, 'locked_users': locked_users}


@app.route('/')
def index():
    err = request.query.get('err')
    if err:
        if err == 'locked':
            error_message = 'This account is locked.'
        elif err == 'banned':
            error_message = "You're banned."
        else:
            error_message = 'Wrong username or password'
    else:
        error_message = None
    return render_index(error_message)


@app.route('/login', method='POST')
def login():
    login = request.forms['login']
    password = request.forms['password']
    success, err = attempt_login(login, password)
    if success:
        return redirect('/mypage')
    else:
        return redirect('/?err=' + err)


@app.route('/mypage')
def mypage():
    if request.get_cookie('login'):
        return render_mypage({
            'last_login_at': str(request.get_cookie('last_login_at')).replace('+', ' '),
            'last_login_ip': request.get_cookie('last_login_ip'),
            'login': request.get_cookie('login'),
        })
    else:
        return redirect('/?err=login_required')


@app.route('/report')
def report():
    response.set_header('Cache-Control', 'no-cache, max-age=0')
    return json.dumps(get_ban_report())


@app.route('/reload', method='POST')
def reload():
    init_data()
    return 'OK'


def execute_command(command):
    if command == 'load':
        load_data()
    elif command == 'initial_banned_ips':
        report = get_ban_report(connect_redis())
        for ip in report['banned_ips']:
            print(ip)
    elif command == 'initial_locked_users':
        report = get_ban_report(connect_redis())
        for user in report['locked_users']:
            print(user)


app = ProxyFix(app)

if __name__ == '__main__':
    load_config()
    init_data()
    import sys
    if len(sys.argv) >= 2:
        execute_command(sys.argv[1])
    else:
        port = int(os.environ.get('PORT', '5000'))
        run(app, debug=1, host='0.0.0.0', port=port)
else:
    load_config()
    init_data()
