from pyzabbix import ZabbixAPI
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import schedule
import time
import json
import os
import sys

with open("config_script_zabbix.json", "r", encoding="utf-8") as file:
        json_data = json.load(file)
        
def send_email(subject, message):
    global json_data
    smtp_server = json_data['smtp_server'] 
    smtp_port = json_data['smtp_port']
    smtp_username = json_data['smtp_username']
    smtp_password = json_data['smtp_password']
    from_email = json_data['from_email']
    to_email = json_data['to_email']
    
    smtp = smtplib.SMTP(smtp_server, smtp_port)
    smtp.starttls()
    smtp.login(smtp_username, smtp_password)

    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(message, "plain"))

    smtp.sendmail(from_email, to_email, msg.as_string())
    
    smtp.quit()
    
last_notification_time = None   
last_notification_time_dict_server = {}
last_notification_time_dict_service = {}
def check_servers():
    global json_data
    global last_notification_time
    global last_notification_time_dict_server
    global last_notification_time_dict_service
    icmp_ping_items_list = []
    zabbix_server = json_data['zabbix_server']
    zabbix_api_user = json_data['zabbix_api_user']
    zabbix_api_password = json_data['zabbix_api_password']

    zapi = ZabbixAPI(zabbix_server)
    zapi.login(zabbix_api_user, zabbix_api_password)

    hosts = zapi.host.get(output='extend')
    for host in hosts:
        try:
            result_string = ''
            not_active_services = {}
            host_id = host['hostid']
            host_name = host['host']
            icmp_ping_items = zapi.item.get(output='extend', 
                                            hostids=host['hostid'], 
                                            search={'key_': 'icmpping'})
                        
            if not icmp_ping_items:
                continue

            icmp_ping_items_list = []

            for item in icmp_ping_items:
                icmp_ping_items_list.append(item['itemid'])

            item = icmp_ping_items_list[2]

            history = zapi.history.get(
                output='extend',
                itemids=item,
                history=0,
                sortfield='clock',
                sortorder='DESC',
                limit=2
            )

            last_ping = history[0]['value']
            last_ping_time = history[0]['clock']
            host_info = zapi.host.get(filter={'host': host_name}, selectInterfaces='extend')
            if host_info:
                host_ip = host_info[0]['interfaces'][0]['ip']
                host_port = host_info[0]['interfaces'][0]['port']
            items = zapi.item.get(filter={"hostid": host_id})
            for item in items:
                if item['key_'].startswith('net') and not item['key_'].startswith('net.if.in'):
                     if item['lastvalue'] != '1':
                        parts = item['key_'].split(',')
                        port = parts[-1].strip('[]')
                        last_ping_time_service = item['lastclock']
                        last_ping_time_formatted_service = datetime.fromtimestamp(int(last_ping_time_service)).strftime('%Y-%m-%d %H:%M:%S')
                        service_name = item['name']
                        not_active_services[service_name] = f"- IP-адрес сервера: [{host_ip}:{port}]\n- Время последнего пинга: [{last_ping_time_formatted_service}]"
                        
            for service_name, info in not_active_services.items():
                    result_string += f"-Имя сервиса: {service_name}\n{info}\n- Текущее состояние: \"Недоступен\"\n\n"
            last_ping_time_formatted = datetime.fromtimestamp(int(last_ping_time)).strftime('%Y-%m-%d %H:%M:%S')
            if float(last_ping) > 0:
                if result_string:
                    current_time = datetime.now()
                    subject = json_data['subject_down_service']
                    message = json_data['message_down_service'].format(
                        host_name=host_name,
                        result_string = result_string)
                    send_time_service_down = json_data['send_time_service_down']
                    if host_name not in last_notification_time_dict_service or \
                        (current_time - last_notification_time_dict_service[host_name]).total_seconds() >= send_time_service_down:
                        send_email(subject, message)
                        last_notification_time_dict_service[host_name] = current_time 
            else:
                send_time_email = json_data['send_time_server_down']
                current_time = datetime.now()
                if host_name not in last_notification_time_dict_server or (current_time - last_notification_time_dict_server[host_name]).total_seconds() >= send_time_email:
                    subject = json_data["subject_down_server"]
                    message = json_data["message_down_server"].format(
                        host_name=host_name,
                        host_ip=host_ip,
                        host_port=host_port,
                        last_ping_time_formatted=last_ping_time_formatted)

                    send_email(subject, message)
                    last_notification_time_dict_server[host_name] = current_time
                    
        except Exception as e:
            send_time_error_script = json_data['send_time_error_script']
            current_time = datetime.now()
            subject = json_data['subject_error_script']
            script_path = os.path.abspath(sys.argv[0])
            message = json_data['message_error_script'].format(
                     e=e,
                   script_path = script_path)
            
            if last_notification_time is None or (current_time - last_notification_time).total_seconds() >= send_time_error_script:
                send_email(subject,message)
                last_notification_time = current_time
            return 1         

schedule.every(15).seconds.do(check_servers)
while True:
    schedule.run_pending()
    time.sleep(1)         
