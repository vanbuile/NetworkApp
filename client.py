import socket
import sys
from threading import Thread
from ftplib import FTP
from messageProtocol import Message, Type, Header
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import ThreadedFTPServer
import os
import json
import time

PORT = 8888
FTPPORT = 21

class Client:
    def __init__(self, server_host, server_port, host, port):
        # Assign basic info
        self.server_host = server_host
        self.server_port = server_port
        self.host = host
        self.port = port
        self.register()
    def run(self):
        self.listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_socket.bind((self.host, self.port))

        if not os.path.exists("downloads/"):
             os.mkdir("downloads/")

        self.files = {}
        self.fpt_t = self.FTPServer(self.host)
        self.fpt_t.start()
        self.lis_t = Thread(target=self.listen)
        self.lis_t.start()
        print("Start getting input")
        self.command()

    def command(self):
        while True:
            request = input("Enter your request:")
            if request == "fetch":
                fName = input("Type file name that you want:")
                self.fetch(fName)
            elif request == "publish":
                lName = input("lName=")
                fName = input("fName=")
                self.publish(lName,fName)
            elif request == "leave":
                self.leave()
                break
    def register(self):
            tmp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                tmp_sock.connect((self.server_host, self.server_port))
            except Exception as e:
                raise Exception(e)

            hostname = socket.gethostname()
            payload = {'hostname': hostname}
            request = Message(Header.REGISTER, Type.REQUEST, payload)
            self.send(request, tmp_sock)

            # Handle server's response
            msg = tmp_sock.recv(2048).decode()
            tmp_sock.close()
            response = Message(None, None,None, msg)
            result = response.get_info()['result']
            if result == 'OK':
                self.hostname = hostname
                print("Running..")
                self.run()
            else:
                raise Exception(f"ERROR when REGISTER: {result}")

    def leave(self):
        tmp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            tmp_sock.connect((self.server_host, self.server_port))
        except:
            return 'CONNECT_SERVER_SOCKET_ERROR'
        payload = {'hostname': self.hostname}
        request = Message(Header.LEAVE, Type.REQUEST, payload)
        self.send(request, tmp_sock)
        #Handle server response
        msg = tmp_sock.recv(2048).decode()
        response = Message(None, None, None, msg)
        result = response.get_info()['result']
        if(result == 'OK'):
            self.exit(0)
        else:
            print("Fail to leave!")
    def listen(self):
        self.listen_socket.listen(5)
        self.active = True
        while self.active:
            try:
                rcv_sock, snd_addr = self.listen_socket.accept()
                new_t = Thread(target=self.reply_conn, args=(rcv_sock, snd_addr))
                new_t.start()
            except OSError:
                break
    def reply_conn(self, rcv_sock, snd_addr):
        try:
            rcv_sock.settimeout(5)
            msg_data = rcv_sock.recv(2048).decode()
            msg = Message(None, None, None, msg_data)
            msg_header = msg.get_header()
            if msg_header == Header.PING and snd_addr[0] == self.server_host:
                self.reply_ping(rcv_sock)
            elif msg_header == Header.DISCOVER and snd_addr[0] == self.server_host:
                self.reply_discover(rcv_sock)
            elif msg_header == Header.RETRIEVE:
                self.reply_retrieve(rcv_sock, msg.get_info())
        except Exception as e:
            print(f"An error occurred when reply connection: {e}")
        finally:
            rcv_sock.close()
    def reply_ping(self, sock):
        payload = {'result': 'Hello'}
        response = Message(Header.PING, Type.RESPONSE, payload)
        self.send(response, sock)
    def reply_discover(self, sock):
        file_list = []
        for f in self.files.keys():
            file_list.append(f)
        payload = {'file_list': file_list}
        response = Message(Header.DISCOVER, Type.RESPONSE, payload)
        self.send(response, sock)
    def reply_retrieve(self, sock, fName):
        payload = {}
        if fName in list(self.files.keys()) and os.path.exists(self.files[fName]):
           rs_msg = 'Accept'
           print('Accept Retrieve')
           payload['lname'] = self.files[fName]
        else:
           rs_msg = 'Deny'
           print('Deny Retrieve')

        payload['result'] = rs_msg

        response = Message(Header.RETRIEVE,Type.RESPONSE, payload)
        self.send(response, sock)

    def send(self, msg: Message, sock:socket):
        encoded_msg = json.dumps(msg.get_packet()).encode()
        dest = 'server' if sock.getpeername()[0] == self.server_host else sock.getpeername()[0]
        try:
            sock.sendall(encoded_msg)
            print(f"Succesfull to send a {msg.get_header().name} message to {dest}" )
            return True
        except:
            print(f"Failed to send a {msg.get_header().name} message to {dest}")
            return False

    def fetch(self, fName):

        # Request server
        payload = { "fname": fName}
        request = Message(Header.FETCH, Type.REQUEST, payload)
        tmp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            tmp_sock.connect((self.server_host, self.server_port))
        except:
            return 'CONNECT_SERVER_SOCKET_ERROR'
        self.send(request, tmp_sock)


        # Handle server's response
        msg = tmp_sock.recv(2048).decode()
        tmp_sock.close()
        response = Message(None, None, None, msg)
        dest_list = response.get_info()['avail_ips']
        if not dest_list:
            print('NO_AVAILABLE_HOST')
            return
        else:
            print(dest_list)
        dest_host = input("Choose a host to retrieve: ")
        self.retrieve(fName, dest_host)

    def retrieve(self, fName, host):
        request = Message(Header.RETRIEVE, Type.REQUEST, fName)
        tmp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            tmp_sock.settimeout(5)
            tmp_sock.connect((host, self.port))
            self.send(request, tmp_sock)
        except:
            return 'UNREACHABLE'

        # If request cannot be sent, return

        # Receive the response
        msg = tmp_sock.recv(2048).decode()
        tmp_sock.close()

        # Process the response
        response = Message(None, None, None, msg)
        result = response.get_info()['result']

        # Check if it accepts or refuses to send the file. If DENIED, try other hosts
        if result == 'DENY':
            print("DENY RETRIEVE FILE")
            return

        # If it has accepted, proceed file transfering using FTP
        lName = response.get_info()['lname']

        # Handle non-existing download directory
        if not os.path.exists("downloads/"):
            os.mkdir("downloads/")

        i = 0
        dest_file = fName
        # Handle duplicate file name
        while os.path.exists("downloads/" + dest_file):
            i += 1
            dest_file = fName + f"({i})"

        # File transfer protocol begins
        ftp = FTP(host)
        ftp.login('admin', 'admin')

        with open("downloads/" + dest_file, 'wb') as f:
            ftp.retrbinary(f'RETR {lName}', f.write)

        ftp.quit()
        # File transfer protocol ends
    def exit(self):
        self.listen_socket.close()
        print("listen socket closed")
        self.active = False
        self.lis_t.join()
        print("listen thread joined")
        self.fpt_t.stop()
        self.fpt_t.join()
        print("FTP server thread joined")
        print("System exited")
        sys.exit()

    def publish(self, lName, fName):
        # Send publish request
        info = {'fname':fName,'lname':lName}
        request = Message(Header.PUBLISH, Type.REQUEST, info)
        tmp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            tmp_sock.connect((self.server_host, self.server_port))
        except:
            return 'CONNECT_SERVER_SOCKET_ERROR'
        self.send(request, tmp_sock)
        # Receive and handle response
        response = tmp_sock.recv(2048).decode()
        tmp_sock.close()
        response = Message(None, None, None, response)
        rs = response.get_info()['result']

        # Publish failed, do not add file to repository
        if rs == "ERROR":
            return rs
        # Pulish success, add file to repository
        self.files[fName] = lName
        # with open("local_files.json", "w") as f:
        #     json.dump(self.files, f, indent=4)
        return rs


    class FTPServer(Thread):
        def __init__(self, host_ip):
            Thread.__init__(self)
            self.host_ip = host_ip
            # Initialize FTP server
            authorizer = DummyAuthorizer()
            authorizer.add_user('admin', 'admin', '.', perm='elradfmwM')
            handler = FTPHandler
            handler.authorizer = authorizer
            handler.banner = "Connect FTP Server Success"
            self.server = ThreadedFTPServer((self.host_ip, FTPPORT), handler)
            self.server.max_cons = 256
            self.server.max_cons_per_ip = 5

        def run(self):
            print(f"FTP Server start on {self.host_ip}:{FTPPORT}")
            self.server.serve_forever()
        def stop(self):
            self.server.close_all()

    # FTP server on another thread

#
SVHOST = '192.168.7.21'
SVPORT = 8888
CLNAME = socket.gethostname()
CLHOST = socket.gethostbyname(CLNAME)
CLPORT = 1111
#
class ClientApp:
    def __init__(self, server_host, server_port, client_host, client_port):
        client = Client(server_host, server_port, client_host, client_port)
def main():
    app = ClientApp(SVHOST, SVPORT, CLHOST, CLPORT)
    print("Here")
    # app.run()
if __name__ == "__main__":
    main()