import sys
import socket
import traceback
import configparser

from random import randrange

from threading import Thread, RLock

from tinydb import TinyDB, Query, where
from tinyrecord import transaction
from helpers.json_message import json_recv, json_send

from inspect import signature

cfg = configparser.ConfigParser()

cfg.read('config.ini')


class GameShopServer:

    def __init__(self):
        self.lock = RLock()

        self.host = cfg['server']['host']
        self.port = int(cfg['server']['port'])
        self.backlog = int(cfg['server']['backlog'])

        self.active_user_sessions = set()

        self.table_shop = TinyDB('data/db.json').table('shop_items')
        self.table_users = TinyDB('data/db.json').table('users')
        self.table_user_goods = TinyDB('data/db.json').table('user_goods')

        self.commands = cfg['server']['commands'].split('\n')

        self.soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        print("Socket created")
        try:
            self.soc.bind((self.host, self.port))
        except:
            print("Bind failed. Error : " + str(sys.exc_info()))
            sys.exit()
        self.soc.listen(self.backlog)

    def start(self):
        while True:
            connection, address = self.soc.accept()
            ip, port = str(address[0]), str(address[1])
            print("Connected with " + ip + ":" + port)

            try:
                Thread(target=self.client_thread, args=(connection, ip, port)).start()
            except:
                print("Thread did not start.")
                traceback.print_exc()

        self.soc.close()

    def serve_query(self, query):
        if query['action'] == 'LOGIN':
            return self.__login(query['params'])
        if not self.__check_user_id(query['user_id']):
            return self.__error('You must sign in first to do this action!')
        if query['action'] not in self.commands:
            return self.__error('Invalid command!')
        if not (query['params'] is None) and not isinstance(query['params'], str):
            return self.__error('Invalid argument!')
        else:
            method = self.__find_method(query['action'])
            if method is None:
                return self.__error('Unexpected error: method \'' + query['action'] + '\' is not found!!!')
            param_count = self.__count_positional_params(signature(method))
            if param_count == 0:
                return method()
            if query['params'] is None and param_count == 1:
                return method(query['user_id'])
            if not (query['params'] is None) and param_count == 2:
                return method(query['user_id'], query['params'])
            return self.__error('Invalid argument count!')

    def client_thread(self, connection, ip, port):
        is_active = True

        while is_active:
            client_query = json_recv(connection)

            if 'LOGOUT' in client_query['action']:
                print("Client is requesting to quit")
                json_send(connection, self.__logout(client_query['user_id']))
                connection.close()
                print("Connection " + ip + ":" + port + " closed")
                is_active = False
            else:
                if 'LOGIN' in client_query['action'] and client_query['user_id'] and self.__check_user_id(
                        client_query['user_id']):
                    json_send(connection,
                              self.__error('You must log out first before signing in to another account!'))
                # with self.lock:
                #     if self.__check_user_id(client_query['user_id']) and client_query['params'] != \
                #             self.table_users.get(doc_id=client_query['user_id'])['name']:
                #         self.__logout(client_query['user_id'])
                else:
                    json_send(connection, self.serve_query(client_query))

    @staticmethod
    def __error(msg):
        return {'status': 'ERR', 'message': msg}

    @staticmethod
    def __success(data, msg=None, uid=None):
        return {'status': 'OK', 'data': data, 'message': msg, 'user_id': uid}

    def __find_method(self, name: str):
        try:
            return self.__getattribute__('_' + self.__class__.__name__ + '__' + name.lower())
        except AttributeError as e:
            return None

    def __count_positional_params(self, sig):
        count = 0
        for param in sig.parameters.values():
            if (param.kind == param.POSITIONAL_OR_KEYWORD and param.default is param.empty):
                count += 1

        return count

    def __check_user_id(self, uid):
        with self.lock:
            return uid in self.active_user_sessions and self.table_users.get(doc_id=uid) is not None

    def __signup(self, nickname):
        with transaction(self.table_users) as tr:
            tr.insert({'name': nickname, 'credits': 0})
        with self.lock:
            user = self.table_users.get(where('name') == nickname)
            return self.__update_credits(user), user.doc_id

    def __login(self, nickname):
        with self.lock:
            user = self.table_users.get(where('name') == nickname)
            if user:
                if user.doc_id in self.active_user_sessions:
                    return self.__error('You already are logged in!')
                else:
                    self.active_user_sessions.add(user.doc_id)
                    success, msg = self.__update_credits(user)
                    if success:
                        return self.__success(self.__inventory(user.doc_id, full_response=False),
                                              msg='Signed in as \'' + nickname + '\'.\n' + msg,
                                              uid=user.doc_id)
                    else:
                        return self.__error(msg)
            else:
                (success, msg), uid = self.__signup(nickname)
                if success:
                    self.active_user_sessions.add(uid)
                    return self.__success(None, msg='Signed up as \'' + nickname + '\'. Welcome!', uid=uid)

    def __logout(self, uid):
        if self.__check_user_id(uid):
            with self.lock:
                self.active_user_sessions.remove(uid)
                return {'status': 'LOGOUT'}
        return self.__error('You must sign in before logging out')

    def __balance(self, uid):
        with self.lock:
            user = self.table_users.get(doc_id=uid)
            return self.__success(None, msg='Credits: ' + str(user['credits']))

    def __shoplist(self, full_response=True):
        with self.lock:
            data = self.table_shop.all()
            if full_response:
                return self.__success(data)
            else:
                return data

    def __inventory(self, uid, full_response=True):
        with self.lock:
            data = []
            for item in self.table_user_goods.search(where('user_id') == uid):
                data.append({'item_name': self.table_shop.get(doc_id=item['item_id'])['name']})
            if full_response:
                if data:
                    return self.__success(data)
                else:
                    return self.__success(None, msg='Your inventory is empty.')
            else:
                return data

    def __update_credits(self, user, rand=True, income=True, amount=None):
        if rand:
            amount = randrange(int(cfg['credits']['min']), int(cfg['credits']['max']), int(cfg['credits']['step']))
        else:
            if amount is None:
                return False, 'Unexpected error'
            amount = abs(amount)
            if not income:
                if amount > user['credits']:
                    return False, 'You don\'t have enough credits to buy this item'
                else:
                    amount = -amount

        with transaction(self.table_users) as tr:
            tr.update({'credits': user['credits'] + amount}, doc_ids=[user.doc_id])
            return True, 'Credits: ' + str(user['credits'] + amount)

    def __buy(self, uid, item_name):
        with self.lock:
            item = self.table_shop.get(where('name') == item_name)
            if item:
                if self.table_user_goods.get((where('user_id') == uid) & (where('item_id') == item.doc_id)) is None:
                    success, msg = self.__update_credits(self.table_users.get(doc_id=uid), rand=False, income=False,
                                                         amount=item['price'])
                    if success:
                        with transaction(self.table_user_goods) as tr:
                            tr.insert({'user_id': uid, 'item_id': item.doc_id})
                        return self.__success(None, 'Successfully bought the \'' + item_name + '\'. ' + msg)
                    else:
                        return self.__error(msg)
                else:
                    return self.__error('You already have that item!')
            else:
                return self.__error('Item doesn\'t exist in the shop!')

    def __sell(self, uid, item_name):
        with self.lock:
            item = self.table_shop.get(where('name') == item_name)
            if item:
                if self.table_user_goods.get((where('user_id') == uid) & (where('item_id') == item.doc_id)) is None:
                    return self.__error('You don\'t have this item!')
                else:
                    success, msg = self.__update_credits(self.table_users.get(doc_id=uid), rand=False,
                                                         amount=item['price'])
                    if success:
                        with transaction(self.table_user_goods) as tr:
                            tr.remove((where('user_id') == uid) & (where('item_id') == item.doc_id))
                        return self.__success(None, 'Successfully sold the \'' + item_name + '\'. ' + msg)
                    else:
                        return self.__error(msg)
            else:
                return self.__error('Item doesn\'t exist in the shop!')
        pass
