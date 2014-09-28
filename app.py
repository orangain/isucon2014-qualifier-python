import MySQLdb
from MySQLdb.cursors import DictCursor
import redis

from flask import (
    Flask, request, redirect, session, url_for, flash, jsonify,
    render_template, _app_ctx_stack
)
from werkzeug.contrib.fixers import ProxyFix

import os, hashlib
from datetime import date, datetime
import time

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

def connect_db():
    host = os.environ.get('ISU4_DB_HOST', 'localhost')
    port = int(os.environ.get('ISU4_DB_PORT', '3306'))
    dbname = os.environ.get('ISU4_DB_NAME', 'isu4_qualifier')
    username = os.environ.get('ISU4_DB_USER', 'root')
    password = os.environ.get('ISU4_DB_PASSWORD', '')
    db = MySQLdb.connect(host=host, port=port, db=dbname, user=username, passwd=password, cursorclass=DictCursor, charset='utf8')
    return db

def connect_redis():
    r = redis.StrictRedis(host='localhost', port=6379, db=0)
    return r

def get_db():
    top = _app_ctx_stack.top
    if not hasattr(top, 'database'):
        top.database = connect_db()
    return top.database


def get_redis():
    top = _app_ctx_stack.top
    if not hasattr(top, 'redis'):
        top.redis = connect_redis()
    return top.redis


def calculate_password_hash(password, salt):
    return hashlib.sha256(password + ':' + salt).hexdigest()


def _user_key(user_id):
    return 'U:{0}'.format(user_id)


def _ip_key(ip):
    return 'IP:{0}'.format(ip)


def login_log(succeeded, login, user_id=None):
    print('login_log: ' + str(succeeded) + ', ' + login + ', ' + str(user_id))
    r = get_redis()
    ip = request.remote_addr
    if succeeded:
        user_key = _user_key(user_id)
        last_login = r.hgetall(user_key)
        current_login = dict(last_login)
        current_login['failure'] = 0
        current_login['last_login_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # time.time()
        current_login['last_login_ip'] = ip
        r.hmset(user_key, current_login)

        ip_key = _ip_key(ip)
        r.hset(ip_key, 'failure', 0)
        return last_login
    elif user_id:
        key = _user_key(user_id)
        r.hincrby(key, 'failure', 1)
    else:
        key = _ip_key(ip)
        r.hincrby(key, 'failure', 1)


#def login_log(succeeded, login, user_id=None):
#    print('login_log: ' + str(succeeded) + ', ' + login + ', ' + str(user_id))
#    db = get_db()
#    cur = db.cursor()
#    cur.execute(
#        'INSERT INTO login_log (`created_at`, `user_id`, `login`, `ip`, `succeeded`) VALUES (NOW(),%s,%s,%s,%s)',
#        (user_id, login, request.remote_addr, 1 if succeeded else 0)
#    )
#    cur.close()
#    db.commit()

def user_locked(user):
    if not user:
        return None
    r = get_redis()
    key = _user_key(user['id'])

    return int(r.hget(key, 'failure') or 0) >= config['user_lock_threshold']

    #cur = get_db().cursor()
    #cur.execute(
    #    'SELECT COUNT(1) AS failures FROM login_log WHERE user_id = %s AND id > IFNULL((select id from login_log where user_id = %s AND succeeded = 1 ORDER BY id DESC LIMIT 1), 0);',
    #    (user['id'], user['id'])
    #)
    #log = cur.fetchone()
    #cur.close()
    #return config['user_lock_threshold'] <= log['failures']


def ip_banned():
    r = get_redis()
    key = _ip_key(request.remote_addr)

    return int(r.hget(key, 'failure') or 0) >= config['ip_ban_threshold']


    #global config
    #cur = get_db().cursor()
    #cur.execute(
    #    'SELECT COUNT(1) AS failures FROM login_log WHERE ip = %s AND id > IFNULL((select id from login_log where ip = %s AND succeeded = 1 ORDER BY id DESC LIMIT 1), 0)',
    #    (request.remote_addr, request.remote_addr)
    #)
    #log = cur.fetchone()
    #cur.close()
    #return config['ip_ban_threshold'] <= log['failures']

def attempt_login(login, password):
    cur = get_db().cursor()
    cur.execute('SELECT * FROM users WHERE login=%s', (login,))
    user = cur.fetchone()
    cur.close()

    if ip_banned():
        if user:
            login_log(False, login, user['id'])
        else:
            login_log(False, login)
        return [None, 'banned']

    if user_locked(user):
        login_log(False, login, user['id'])
        return [None, 'locked']

    if user and calculate_password_hash(password, user['salt']) == user['password_hash']:
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

def current_user():
    if not session['user_id']:
        return None
    cur = get_db().cursor()
    cur.execute('SELECT * FROM users WHERE id=%s', (session['user_id'],))
    user = cur.fetchone()
    cur.close()
    if user:
        return user
    else:
        return None

def last_login():
    user = current_user()
    if not user:
        return None

    cur = get_db().cursor()
    cur.execute(
        'SELECT * FROM login_log WHERE succeeded = 1 AND user_id = %s ORDER BY id DESC LIMIT 2',
        (user['id'],)
    )
    rows = cur.fetchall()
    cur.close()
    return rows[-1]

def banned_ips():
    global config
    threshold = config['ip_ban_threshold']

    cur = get_db().cursor()
    cur.execute(
        'SELECT ip FROM (SELECT ip, MAX(succeeded) as max_succeeded, COUNT(1) as cnt FROM login_log GROUP BY ip) AS t0 WHERE t0.max_succeeded = 0 AND t0.cnt >= %s',
        (threshold,)
    )
    not_succeeded = cur.fetchall()
    ips = map(lambda x: x['ip'], not_succeeded)

    cur.execute('SELECT ip, MAX(id) AS last_login_id FROM login_log WHERE succeeded = 1 GROUP by ip')
    last_succeeds = cur.fetchall()

    for row in last_succeeds:
        cur.execute('SELECT COUNT(1) AS cnt FROM login_log WHERE ip = %s AND %s < id', (row['ip'], row['last_login_id']))
        count = cur.fetchone()['cnt']
        if threshold <= count:
            ips.append(row['ip'])

    cur.close()
    return ips

def locked_users():
    global config
    threshold = config['user_lock_threshold']

    cur = get_db().cursor()
    cur.execute(
        'SELECT user_id, login FROM (SELECT user_id, login, MAX(succeeded) as max_succeeded, COUNT(1) as cnt FROM login_log GROUP BY user_id) AS t0 WHERE t0.user_id IS NOT NULL AND t0.max_succeeded = 0 AND t0.cnt >= %s',
        (threshold,)
    )
    not_succeeded = cur.fetchall()
    ips = map(lambda x: x['login'], not_succeeded)

    cur.execute('SELECT user_id, login, MAX(id) AS last_login_id FROM login_log WHERE user_id IS NOT NULL AND succeeded = 1 GROUP BY user_id')
    last_succeeds = cur.fetchall()

    for row in last_succeeds:
        cur.execute('SELECT COUNT(1) AS cnt FROM login_log WHERE user_id = %s AND %s < id', (row['user_id'], row['last_login_id']))
        count = cur.fetchone()['cnt']
        if threshold <= count:
            ips.append(row['login'])

    cur.close()
    return ips

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
        print('err = ' + err)
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
        #user = {'login': session['login']}
        #last_login = {'created_at': session['last_login_at', 'ip': session['last_login_ip']}
        #return render_template('mypage.html', user=user, last_login=last_login())
        return render_template('mypage.html', session=session)
    else:
        flash('You must be logged in')
        return redirect(url_for('index'))

    #user = current_user()
    #if user:
    #    return render_template('mypage.html', user=user, last_login=last_login())
    #else:
    #    flash('You must be logged in')
    #    return redirect(url_for('index'))

@app.route('/report')
def report():
    response = jsonify({ 'banned_ips': banned_ips(), 'locked_users': locked_users() })
    response.status_code = 200
    return response

if __name__ == '__main__':
    load_config()
    port = int(os.environ.get('PORT', '5000'))
    app.run(debug=1, host='0.0.0.0', port=port)
else:
    load_config()
