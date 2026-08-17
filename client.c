#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <netinet/in.h>

#define BUF_SIZE 1024

void send_file(FILE *fp, int sockfd)
{
    char data[BUF_SIZE] = {0};
    while (fgets(data, BUF_SIZE, fp) != NULL)
    {
        if (send(sockfd, data, strlen(data), 0) == -1)
        {
            printf("Error in sending.\n");
            exit(1);
        }
        bzero(data, BUF_SIZE);
    }
    if (shutdown(sockfd, SHUT_WR) == -1)
    {
        perror("Error shutting down socket.");
        return;
    }
}

int main(int argc, char *argv[])
{
    if (argc != 4)
    {
        printf("Usage: %s <server_ip> <server_port> <file_name>\n", argv[0]);
        return -1;
    }

    char *ip = argv[1];
    int port = atoi(argv[2]);
    char *file_name = argv[3];

    int sock, ret;
    struct sockaddr_in serv_addr;
    char *message = "hello";
    char buffer[BUF_SIZE] = {0};

    if ((sock = socket(AF_INET, SOCK_STREAM, 0)) < 0)
    {
        printf("Socket creation error\n");
        return -1;
    }

    serv_addr.sin_family = AF_INET;
    serv_addr.sin_port = htons(port);

    if (inet_pton(AF_INET, ip, &serv_addr.sin_addr) <= 0)
    {
        printf("Invalid address/ Address not supported\n");
        return -1;
    }

    if (connect(sock, (struct sockaddr *)&serv_addr, sizeof(serv_addr)) < 0)
    {
        printf("Connection Failed\n");
        return -1;
    }

    FILE *fp = fopen(file_name, "r");
    if (fp == NULL)
    {
        printf("Error in file reading");
        exit(1);
    }

    send_file(fp, sock);

    ret = recv(sock, buffer, BUF_SIZE, 0);
    if (ret == -1)
    {
        printf("Failed to receive message\n");
        return -1;
    }

    printf("Results: %s\n", buffer);

    fclose(fp);
    close(sock);

    return 0;
}
