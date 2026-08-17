#include <stdio.h>
#include <stdlib.h>

int main(int argc, char *argv[])
{
    if (argc < 2)
    {
        printf("usage: ./filename <input_string>");
    }
    int number = atoi(argv[1]);
    printf("%d", number * number);
    return 0;
}