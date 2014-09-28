import redis

from flask import (
    Flask, request, redirect, session, url_for, flash, jsonify,
    render_template, _app_ctx_stack
)
from werkzeug.contrib.fixers import ProxyFix

import os
import hashlib
from datetime import datetime

config = {}
app = Flask(__name__, static_url_path='')
app.wsgi_app = ProxyFix(app.wsgi_app)
app.secret_key = os.environ.get('ISU4_SESSION_SECRET', 'shirokane')


def load_config():
    global config
    config = {
        'user_lock_threshold': int(os.environ.get('ISU4_USER_LOCK_THRESHOLD', 3)),
        'ip_ban_threshold': int(os.environ.get('ISU4_IP_BAN_THRESHOLD', 10))
    }
    return config


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

    r = connect_redis()
    r.flushall()

    load_users(r)

    cur = connect_db().cursor()
    cur.execute('SELECT * FROM login_log')
    for row in cur.fetchall():
        login_log(bool(row['succeeded']), row['login'], row['user_id'],
                  row['ip'], row['created_at'], r)

    cur.close()


def load_users(r):
    with open('/home/isucon/sql/dummy_users.tsv') as f:
        for line in f:
            id, login, password, salt, password_hash = line.rstrip().split('\t')
            user_key = _user_key(login)
            r.hmset(user_key, {
                'id': id,
                'login': login,
                'passwd': password,
                'failure': 0,
            })


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
        user_key = _user_key(login)
        r.hincrby(user_key, 'failure', 1)

        ip_key = _ip_key(ip)
        r.hincrby(ip_key, 'failure', 1)
    else:
        ip_key = _ip_key(ip)
        r.hincrby(ip_key, 'failure', 1)


def user_locked(user):
    if not user:
        return None
    return int(user.get('failure', 0)) >= config['user_lock_threshold']


def ip_banned():
    r = get_redis()
    key = _ip_key(request.remote_addr)

    return int(r.hget(key, 'failure') or 0) >= config['ip_ban_threshold']


def attempt_login(login, password):
    r = get_redis()
    user_key = _user_key(login)
    user = r.hgetall(user_key) or None

    if ip_banned():
        if user:
            login_log(False, login, user['id'])
        else:
            login_log(False, login)
        return [None, 'banned']

    if user_locked(user):
        login_log(False, login, user['id'])
        return [None, 'locked']

    if user and password == user['passwd']:
        last_login = login_log(True, login, user['id'])
        session['user_login'] = login
        session['last_login_at'] = last_login.get('last_login_at')
        session['last_login_ip'] = last_login.get('last_login_ip')
        return [user, None]
    elif user:
        login_log(False, login, user['id'])
        return [None, 'wrong_password']
    else:
        login_log(False, login)
        return [None, 'wrong_login']


def get_ban_report():
    banned_ips = []
    locked_users = []

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
    return render_template('index.html')


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
        if err == 'locked':
            flash('This account is locked.')
        elif err == 'banned':
            flash("You're banned.")
        else:
            flash('Wrong username or password')
        return redirect(url_for('index'))


@app.route('/mypage')
def mypage():
    if session['user_id']:
        return render_template('mypage.html', session=session)
    else:
        flash('You must be logged in')
        return redirect(url_for('index'))


@app.route('/report')
def report():
    response = jsonify(get_ban_report())
    response.status_code = 200
    return response

if __name__ == '__main__':
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == 'load':
        load_data()
    else:
        load_config()
        port = int(os.environ.get('PORT', '5000'))
        app.run(debug=1, host='0.0.0.0', port=port)
else:
    load_config()
