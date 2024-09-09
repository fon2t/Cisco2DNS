###################################
# Cisco DHCP to Hostfile
#
# Nick Route 16 December 2023
#
##################################
# Needs Paramiko library
# install via pip install paramikoimport paramiko
import logging, sys
import datetime, time
import paramiko
import re
import os
import subprocess

#############################
# Connect to device using ssh
#############################
def ssh_connect(hostname, username, password):
    try:
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(hostname, username=username, password=password, timeout=10, port=port)
        return ssh_client
    except paramiko.AuthenticationException:
        logging.error("Authentication failed. Please check your credentials.")
        return None
    except paramiko.SSHException as e:
        logging.error(f"SSH: Error connecting to {hostname}: {e}")
        return None

def retrieve_dhcp_pool_config(ssh_client):
    try:
        logging.info("SSH: Retrieving DHCP configuration")
        stdin, stdout, stderr = ssh_client.exec_command("show running-config | include ip dhcp pool | host")
        dhcp_config = stdout.read().decode("utf-8")
        logging.info("SSH: Retrieved DHCP configuration")
        return dhcp_config
    except paramiko.SSHException as e:
        logging.error(f"SSH: Error retrieving DHCP pool configuration: {e}")
        return None

def read_existing_host_file(existing_file):
    try:
        with open(existing_file, 'r') as file:
            return file.read()
    except FileNotFoundError:
        return ""


def convert_to_host_file(dhcp_config, existing_content):
    lines = dhcp_config.split('\n')
    in_dhcp_pool = False
    host_entries = []
    unix_hosts = ""

    for line in lines:
        line = line.strip()
        pool_match = re.match(r"\s*ip dhcp pool (.+)$", line)
        if pool_match:
            in_dhcp_pool = True
            pool_name = pool_match.group(1).lower()
        elif in_dhcp_pool and re.match(r"\s*host ([^\s]+) ([^\s]+)", line):
            entry = re.match(r"\s*host ([^\s]+) ([^\s]+)", line)
            ip_address, netmask = entry.group(1), entry.group(2)
            host_entries.append((ip_address, pool_name + dnsdomain))
        # elif in_dhcp_pool and re.match(r"!", line):
        elif in_dhcp_pool:
            in_dhcp_pool = False

    # Sort entries by the second, third, and fourth octets of the IP address
    # sorted_entries = sorted(host_entries, key=lambda x: (int(x[0].split('.')[2]), int(x[0].split('.')[3])))
    sorted_entries = sorted(host_entries, key=lambda x: tuple(map(int, x[0].split('.')[1:])))

    # Create file header
    header = f"# Auto created host file \n"
    header += f"# Generated from switch dhcp configuration \n"
    header += f"# Generated on {now} \n"
    
    # Create the Unix-style host file
    unix_hosts = header + existing_content + "\n".join([f"{ip} {hostname}" for ip, hostname in sorted_entries])

    return unix_hosts



def write_to_file(file_path, content):
    with open(file_path, 'w', newline=os.linesep) as file:
        file.write(content)


def execute_unix_commands(chown_cmd, chgrp_cmd, restart_cmd):
    try:
        subprocess.run(chown_cmd, check=True, shell=True)
        subprocess.run(chgrp_cmd, check=True, shell=True)
        subprocess.run(restart_cmd, check=True, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"Error executing Unix commands: {e}")

#############################
# Main Parameters
#############################

# Date - used for filename
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
# SSH port
port=22
# SSH parameters
hostname = "<ip address>"
username = "cisco"
password = "password"
# DNS subdomain - leave blank if you don't want one
# Leading "." is required
dnsdomain = ".home.arpa"
# Enable logging
# logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
# File parameters
existing_host_file = "./default_hosts.txt"
# output_file = "./hosts.txt"  # Specify the desired output file path
output_file = "/etc/pihole/custom.list"  # Specify the desired output file path
# Unix commands
chown_cmd = "chown pihole:pihole " + output_file
chgrp_cmd = "chgrp pihole " + output_file
# restart_cmd = "sudo systemctl restart your_process"
restart_cmd = "sudo pihole restartdns"


#############################
# Main Routine
#############################
def main():

    ssh_client = ssh_connect(hostname, username, password)
    
    if ssh_client:
        dhcp_config = retrieve_dhcp_pool_config(ssh_client)
        base_host_file = read_existing_host_file(existing_host_file)

        if dhcp_config:
            host_file = convert_to_host_file(dhcp_config, base_host_file)
            logging.info("FUNCTION: Converted Cisco configuration to Unix style host file:\n")
            logging.debug(host_file)

            write_to_file(output_file, host_file)
            logging.info(f"FILEIO: Host file written to: {output_file}")
        
            # Execute Unix commands
            execute_unix_commands(chown_cmd, chgrp_cmd, restart_cmd)

        ssh_client.close()
if __name__ == "__main__":
    main()
