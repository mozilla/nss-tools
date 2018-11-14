#!/bin/bash

if [ "$1" == "1" ]; then
	### STEP 1 ###
	cd

	# set-up docker-worker things
	mkdir hello-world-aarch64 && cd hello-world-aarch64
	echo "FROM aarch64/hello-world" > Dockerfile
	docker build -t taskcluster/livelog:v4 .

	cd

	# build 0.12.8 from source
	git clone git@github.com:franziskuskiefer/node.git
	cd node
	git checkout v0.12.18-aarch64
	./configure --dest-cpu=arm64 --openssl-no-asm
	make -j100 # this will fail
	sed -i '/-m64/d' out/deps/v8/tools/gyp/*.mk
	make -j100
else
	### STEP 2 ###

	# get docker-worker set-up
	cd
	git clone https://github.com/franziskuskiefer/docker-worker.git
	cd docker-worker/ && git checkout origin/aarch64
	npm install
	cd
	npm install babel@4.7
	./start-worker.sh
fi

