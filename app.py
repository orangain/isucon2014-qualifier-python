# coding: utf-8

import redis

from flask import (
    Flask, request, redirect, session, url_for, flash, jsonify,
    _app_ctx_stack, Response
)
from werkzeug.contrib.fixers import ProxyFix

import os
import hashlib
from datetime import datetime

from views import render_index, render_mypage


config = {}
app = Flask(__name__, static_url_path='')
app.wsgi_app = ProxyFix(app.wsgi_app)
app.secret_key = os.environ.get('ISU4_SESSION_SECRET', 'shirokane')

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
    top = _app_ctx_stack.top
    if not hasattr(top, 'redis'):
        top.redis = connect_redis()
    return top.redis


def calculate_password_hash(password, salt):
    return hashlib.sha256(password + ':' + salt).hexdigest()


def _user_key(user_login):
    return 'U:{0}'.format(user_login)


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
        #print('login_log: ' + str(succeeded) + ', ' + login + ', ' + str(user_id) + ', ' + ip)
        if succeeded:
            user_key = _user_key(login)
            last_login = r.hgetall(user_key)
            current_login = dict(last_login)
            current_login['failure'] = 0
            current_login['last_login_at'] = now.strftime("%Y-%m-%d %H:%M:%S")
            current_login['last_login_ip'] = ip
            r.hmset(user_key, current_login)

            ip_key = _ip_key(ip)
            r.hset(ip_key, 'failure', 0)
            return last_login
        elif user_id:
            pipe = r.pipeline()
            user_key = _user_key(login)
            pipe.hincrby(user_key, 'failure', 1)

            ip_key = _ip_key(ip)
            pipe.hincrby(ip_key, 'failure', 1)
            pipe.execute()
        else:
            ip_key = _ip_key(ip)
            r.hincrby(ip_key, 'failure', 1)

    r = connect_redis()
    r.flushall()

    for id, login, password, salt, password_hash in load_users():
        user_key = _user_key(login)
        r.hmset(user_key, {
            'id': id,
            'login': login,
            'passwd': password,
            'failure': 0,
        })

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


def user_locked(r, user_key):
    #if not user:
    #    return None
    #return int(user.get('failure', 0)) >= config['user_lock_threshold']
    if user_key in LOCKED_USERS:
        return True

    locked = int(r.hget(user_key, 'failure') or 0) >= config['user_lock_threshold']
    if locked:
        LOCKED_USERS.add(user_key)

    return locked


def ip_banned(r, ip_key):
    #r = get_redis()
    #key = _ip_key(request.remote_addr)
    if ip_key in BANNED_IPS:
        return True

    banned = int(r.hget(ip_key, 'failure') or 0) >= config['ip_ban_threshold']
    if banned:
        BANNED_IPS.add(ip_key)

    return banned


def attempt_login(login, password):
    r = get_redis()
    user_key = _user_key(login)
    #user = r.hgetall(user_key) or None
    user_password = PASSWORDS.get(login)
    ip = request.remote_addr
    ip_key = _ip_key(ip)

    #def ip_banned():
    #    return int(r.hget(ip_key, 'failure') or 0) >= config['ip_ban_threshold']

    if ip_banned(r, ip_key):
        if user_password:
            #user_key = _user_key(login)
            r.hincrby(user_key, 'failure', 1)
        return [None, 'banned']

    if not user_password:
        r.hincrby(ip_key, 'failure', 1)
        #return [None, 'wrong_login']
        return [None, 'wrong_login_or_password']

    # when user exists

    #user = r.hgetall(user_key) or None

    #def user_locked(user):
    #    return int(user.get('failure', 0)) >= config['user_lock_threshold']

    if user_locked(r, user_key):
        #ip_key = _ip_key(ip)
        r.hincrby(ip_key, 'failure', 1)
        return [None, 'locked']

    if user_password and password == user_password:
        user = r.hgetall(user_key) or None
        session['login'] = login
        session['last_login_at'] = user.get('last_login_at')
        session['last_login_ip'] = user.get('last_login_ip')
        #user['failure'] = 0
        #user['last_login_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        #user['last_login_ip'] = ip

        pipe = r.pipeline()
        pipe.hset(user_key, 'failure', 0)
        pipe.hset(user_key, 'last_login_at', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        pipe.hset(user_key, 'last_login_ip', ip)
        #pipe.hmset(user_key, user)

        #ip_key = _ip_key(ip)
        pipe.hset(ip_key, 'failure', 0)
        pipe.execute()
        return [user, None]
    #elif user:
    else:
        pipe = r.pipeline()
        pipe.hincrby(user_key, 'failure', 1)

        #ip_key = _ip_key(ip)
        pipe.hincrby(ip_key, 'failure', 1)
        pipe.execute()
        #return [None, 'wrong_password']
        return [None, 'wrong_login_or_password']
    #else:
    #    ip_key = _ip_key(ip)
    #    r.hincrby(ip_key, 'failure', 1)
    #    return [None, 'wrong_login']


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
            if int(r.hget(key, 'failure')) >= config['user_lock_threshold']:
                locked_users.append(key_id)
        elif key_type == 'IP':
            if int(r.hget(key, 'failure')) >= config['ip_ban_threshold']:
                banned_ips.append(key_id)

    return {'banned_ips': banned_ips, 'locked_users': locked_users}


@app.route('/')
def index():
    #return render_template('index.html')
    err = request.args.get('err')
    if err:
        if err == 'locked':
            error_message = 'This account is locked.'
        elif err == 'banned':
            error_message = "You're banned."
        else:
            error_message = 'Wrong username or password'
    else:
        error_message = None
    return Response(render_index(error_message))


@app.route('/login', methods=['POST'])
def login():
    login = request.form['login']
    password = request.form['password']
    user, err = attempt_login(login, password)
    if user:
        session['user_id'] = user['id']
        return redirect(url_for('mypage'))
    else:
        #print('err = ' + err)
        return redirect(url_for('index') + '?err=' + err)

        #if err == 'locked':
        #    flash('This account is locked.')
        #elif err == 'banned':
        #    flash("You're banned.")
        #else:
        #    flash('Wrong username or password')
        #return redirect(url_for('index'))


@app.route('/mypage')
def mypage():
    if session.get('user_id'):
        #return render_template('mypage.html', session=session)
        return Response(render_mypage())
    else:
        flash('You must be logged in')
        return redirect(url_for('index'))


@app.route('/report')
def report():
    response = jsonify(get_ban_report())
    response.status_code = 200
    response.headers['Cache-Control'] = 'no-cache, max-age=0'
    return response


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


if __name__ == '__main__':
    load_config()
    import sys
    if len(sys.argv) >= 2:
        execute_command(sys.argv[1])
    else:
        port = int(os.environ.get('PORT', '5000'))
        app.run(debug=1, host='0.0.0.0', port=port)
else:
    load_config()
    init_data()
