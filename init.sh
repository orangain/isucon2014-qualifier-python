#!/bin/sh
set -x
set -e
cd $(dirname $0)

#myuser=root
#mydb=isu4_qualifier
#myhost=127.0.0.1
#myport=3306
#mysql -h ${myhost} -P ${myport} -u ${myuser} -e "DROP DATABASE IF EXISTS ${mydb}; CREATE DATABASE ${mydb}"
#mysql -h ${myhost} -P ${myport} -u ${myuser} ${mydb} < sql/schema.sql
#mysql -h ${myhost} -P ${myport} -u ${myuser} ${mydb} < sql/dummy_users.sql
#mysql -h ${myhost} -P ${myport} -u ${myuser} ${mydb} < sql/dummy_log.sql

sudo service redis-server stop
sleep 1
sudo cp appendonly.aof  /var/lib/redis/
sudo service redis-server start

#python webapp/python/app.py load

# Restart server to clear cache on memory
CURRENT_APP=$(sudo supervisorctl status |grep RUNNING|cut -d " " -f 1)
sudo supervisorctl restart $CURRENT_APP
sleep 1

# Make cache in varnish
curl -o /dev/null http://localhost/stylesheets/isucon-bank.css
curl -o /dev/null http://localhost/stylesheets/bootstrap.min.css
curl -o /dev/null http://localhost/stylesheets/bootflat.min.css
curl -o /dev/null http://localhost/stylesheets/isucon-bank.css
curl -o /dev/null http://localhost/images/isucon-bank.png
curl -o /dev/null http://localhost/
curl -o /dev/null http://localhost/?err=locked
curl -o /dev/null http://localhost/?err=banned
curl -o /dev/null http://localhost/?err=wrong_login_or_password
curl -o /dev/null http://localhost/?err=login_required

sleep 1
