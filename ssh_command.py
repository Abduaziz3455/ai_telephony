import logging

import paramiko
from paramiko.ssh_exception import AuthenticationException
from environs import Env

env = Env()
env.read_env()


def ssh_connect_B(command: str, command2: str = None):
    hostname = env.str('HOST_B')
    username = env.str('USERNAME')
    private_key_path = env.str('KEY_PATH_B')

    try:
        # Load the private key
        private_key = paramiko.RSAKey.from_private_key_file(private_key_path)

        # Create an SSH client
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Connect to the server using the private key
        client.connect(hostname, username=username, pkey=private_key, timeout=20)

        # Execute a command
        stdin, stdout, stderr = client.exec_command(command)
        output = stdout.read().decode()
        logging.info(output)
        if command2:
            client.exec_command(command2)
    except AuthenticationException:
        logging.info("Authentication failed")
    except Exception as e:
        logging.info("Error connecting to host B: " + str(e))
    finally:
        # Close the connection
        client.close()
