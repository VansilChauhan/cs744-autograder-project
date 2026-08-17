#!/bin/bash

SERVER_IP="127.0.0.1"
SERVER_PORT="8080"
CLIENT="./client.o"

for ((i = 1; i <= $1; i++)); do
    CURR=$(($i % 4 + 1))
    echo $CURR
done | xargs -P 10 -I {} bash -c "${CLIENT} $SERVER_IP $SERVER_PORT program_{}.c"
