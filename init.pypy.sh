#!/bin/sh
set -x
set -e
cd $(dirname $0)

reset_redis() {
	sudo service redis-server stop
	sleep 1
	sudo cp appendonly.aof  /var/lib/redis/
	sudo service redis-server start
}

echo "Reset data on Redis"
reset_redis

echo "Restart server to clear cache"
CURRENT_APP=$(sudo supervisorctl status |grep RUNNING|cut -d " " -f 1)
sudo supervisorctl restart $CURRENT_APP
sleep 1

echo "Warm up JIT"
~/continuous-profiler/vendor/double/double -b "~/benchmarker bench --init=/home/isucon/init.subprocess.sh --workload 10" sleep 25

echo "Reset data on Redis"
reset_redis

echo "Clean cache without restarting"

WORKERS=$(cat ~/webapp/python/gunicorn_config.py|grep ^workers|cut -d = -f 2| awk '{print $1}')

#seq $(expr 10 "*" $WORKERS) | xargs -n 1 -P $WORKERS -I % curl -X POST http://localhost:8080/reload
#for i in `seq 100` ; do
#	curl -X POST http://localhost/reload
#done
curl -X POST http://localhost:8080/reload

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

sleep 3
