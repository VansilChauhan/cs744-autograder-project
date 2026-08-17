#!/bin/bash
make clean
make
./server.o 8080 1000 solution.c test_cases.txt
