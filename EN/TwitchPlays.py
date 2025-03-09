# Hey! Duty here! This program that lets Twitch or YouTube play is based on DougDoug's one that I adapted according to my needs!
# It's probably not the most optimimal and the easiest to understand or put in place, but it works very well.
# I'd recommend not to modify anything (apart from the variable that are made for it), it works very good with the actual ones.
# On that note, have a good live and good luck to the chat!


import requests
import socket
import re
import random
import time
import json
import concurrent.futures
from pywinauto import Application, Desktop
from pywinauto.findwindows import ElementNotFoundError
from sys import exit
import pyautogui


########################## CONNECTION ##########################
# DougDoug note:
# This is the part of the code that connects to Twitch or YouTube and checks for new messages.
# You should not need to modify anything in this part, just use it as it is.
# This code is based on Wituz's "Twitch Plays" tutorial, updated (Duty here - originally for Python 3.9.XX but I updated it for 3.13.XX).
# http://www.wituz.com/make-your-own-twitch-plays-stream.html (this link is dead).
# Updated for YouTube by DDarknut, with help from Ottomated.


MAX_TIME_TO_WAIT_FOR_LOGIN = 3
YOUTUBE_FETCH_INTERVAL = 1

class Twitch:
    re_prog = None
    sock = None
    partial = b''
    login_ok = False
    channel = ''
    login_timestamp = 0

    def twitch_connect(self, channel):
        if self.sock: self.sock.close()
        self.sock = None
        self.partial = b''
        self.login_ok = False
        self.channel = channel

        # Compile regular expressions.
        self.re_prog = re.compile(b'^(?::(?:([^ !\r\n]+)![^ \r\n]*|[^ \r\n]*) )?([^ \r\n]+)(?: ([^:\r\n]*))?(?: :([^\r\n]*))?\r\n', re.MULTILINE)

        # Create socket.
        print('Connecting to Twitch...')
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Attempt to connect socket.
        self.sock.connect(('irc.chat.twitch.tv', 6667))

        # Log in anonymously.
        user = 'justinfan%i' % random.randint(10000, 99999)
        print('Connected to Twitch. Logging in anonymously...')
        self.sock.send(('PASS asdf\r\nNICK %s\r\n' % user).encode())

        self.sock.settimeout(1.0/60.0)

        self.login_timestamp = time.time()

    # Attempt to reconnect after a delay.
    def reconnect(self, delay):
        time.sleep(delay)
        self.twitch_connect(self.channel)

    # Returns a list of received irc messages.
    def receive_and_parse_data(self):
        buffer = b''
        while True:
            received = b''
            try:
                received = self.sock.recv(4096)
            except socket.timeout:
                break
            # except OSError as e:
            #     if e.winerror == 10035:
            #         # This "error" is expected - it's received if timeout is set to zero, and there is no data to read on the socket.
            #         break
            except Exception as e:
                print('Unexpected connection error. Reconnecting in a second...', e)
                self.reconnect(1)
                return []
            if not received:
                print('Connection closed by Twitch. Reconnecting in 5 seconds...')
                self.reconnect(5)
                return []
            buffer += received

        if buffer:
            # Prepend unparsed data from previous iterations.
            if self.partial:
                buffer = self.partial + buffer
                self.partial = 0


            # Parse irc messages.
            res = []
            matches = list(self.re_prog.finditer(buffer))
            for match in matches:
                res.append({
                    'name':     (match.group(1) or b'').decode(errors='replace'),
                    'command':  (match.group(2) or b'').decode(errors='replace'),
                    'params':   list(map(lambda p: p.decode(errors='replace'), (match.group(3) or b'').split(b' '))),
                    'trailing': (match.group(4) or b'').decode(errors='replace'),
                })

            # Save data that couldn't be parsed for the next iteration.
                self.partial + buffer == buffer
            else:
                end = matches[-1].end()
                if end < len(buffer):
                    self.partial = buffer[end:]

                if matches[0].start() != 0:
                    # If we get here, a message has maybe been forgotten.
                    print('A message has maybe been forgotten.')

            return res

        return []

    def twitch_receive_messages(self):
        privmsgs = []
        for irc_message in self.receive_and_parse_data():
            cmd = irc_message['command']
            if cmd == 'PRIVMSG':
                privmsgs.append({
                    'username': irc_message['name'],
                    'message': irc_message['trailing'],
                })
            elif cmd == 'PING':
                self.sock.send(b'PONG :tmi.twitch.tv\r\n')
            elif cmd == '001':
                print('Successfully logged in. Joining channel ' + self.channel + '.')
                self.sock.send(('JOIN #%s\r\n' % self.channel).encode())
                self.login_ok = True
            elif cmd == 'JOIN':
                print('Channel ' + self.channel + ' joined successfully.')
                # Looks if the window specified below exists, if not prints the list of all the opened windows.
                def window_exists(WINDOW_TITLE):
                    try:
                        app = Application(backend="uia").connect(title=WINDOW_TITLE)
                        app.window(title=WINDOW_TITLE)
                        return True
                    except ElementNotFoundError:
                        return False
                    except Exception as e:
                        print(f"Unexpected error: {e}")
                        return False
                if not window_exists(WINDOW_TITLE):
                    print('Window with title "' + WINDOW_TITLE + '" not found. List of all windows: ' + str([w.window_text() for w in Desktop(backend="uia").windows()]) + '.')
                    exit()
            elif cmd == 'NOTICE':
                print('Server notice:', irc_message['params'], irc_message['trailing'], ".")
            elif cmd == '002': continue
            elif cmd == '003': continue
            elif cmd == '004': continue
            elif cmd == '375': continue
            elif cmd == '372': continue
            elif cmd == '376': continue
            elif cmd == '353': continue
            elif cmd == '366': continue
            else:
                print('Unhandled irc message: ', irc_message, ".")

        if not self.login_ok:
            # The program is still waiting for the initial login message. If it's waited longer than it should, try to reconnect.
            if time.time() - self.login_timestamp > MAX_TIME_TO_WAIT_FOR_LOGIN:
                print('No response from Twitch. Reconnecting...')
                self.reconnect(0)
                return []

        return privmsgs

# Thanks to Ottomated for helping with the YouTube side of the code!
class YouTube:
    session = None
    config = {}
    payload = {}

    thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fetch_job = None
    next_fetch_time = 0

    re_initial_data = re.compile('(?:window\\s*\\[\\s*[\\"\']ytInitialData[\\"\']\\s*\\]|ytInitialData)\\s*=\\s*({.+?})\\s*;')
    re_config = re.compile('(?:ytcfg\\s*.set)\\(({.+?})\\)\\s*;')

    def get_continuation_token(self, data):
        cont = data['continuationContents']['liveChatContinuation']['continuations'][0]
        if 'timedContinuationData' in cont:
            return cont['timedContinuationData']['continuation']
        else:
            return cont['invalidationContinuationData']['continuation']

    def reconnect(self, delay):
        if self.fetch_job and self.fetch_job.running():
            if not self.fetch_job.cancel():
                print("Waiting for fetch job to finish...")
                self.fetch_job.result()
        print(f"Retrying in {delay}...")
        if self.session: self.session.close()
        self.session = None
        self.config = {}
        self.payload = {}
        self.fetch_job = None
        self.next_fetch_time = 0
        time.sleep(delay)
        self.youtube_connect(self.channel_id, self.stream_url)

    def youtube_connect(self, channel_id, stream_url=None):
        print("Connecting to YouTube...")

        self.channel_id = channel_id
        self.stream_url = stream_url

        # Create http client session.
        self.session = requests.Session()
        # Spoof user agent so YouTube thinks it's a browser.
        self.session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Safari/537.36'
        # Add consent cookie to bypass Google's consent page.
        requests.utils.add_dict_to_cookiejar(self.session.cookies, {'CONSENT': 'YES+'})

        # Connect using stream_url "stream_url" if provided, otherwise use "channel_id".
        if stream_url is not None:
            live_url = self.stream_url
        else:
            live_url = f"https://youtube.com/channel/{self.channel_id}/live"

        res = self.session.get(live_url)
        if res.status_code == 404:
            live_url = f"https://youtube.com/c/{self.channel_id}/live"
            res = self.session.get(live_url)
        if not res.ok:
            if stream_url is not None:
                print(f"Couldn't load the stream URL ({res.status_code} {res.reason}). Is the stream URL ({self.stream_url}) correct?")
            else:
                print(f"Couldn't load livestream page ({res.status_code} {res.reason}). Is the channel ID ({self.channel_id}) correct?")
            time.sleep(5)
            exit(1)
        livestream_page = res.text

        # Find initial data in the livestream page.
        matches = list(self.re_initial_data.finditer(livestream_page))
        if len(matches) == 0:
            print("Couldn't find initial data in the livestream page.")
            time.sleep(5)
            exit(1)
        initial_data = json.loads(matches[0].group(1))

        # Get continuation token for the live chat iframe.
        iframe_continuation = None
        try:
            iframe_continuation = initial_data['contents']['twoColumnWatchNextResults']['conversationBar']['liveChatRenderer']['header']['liveChatHeaderRenderer']['viewSelector']['sortFilterSubMenuRenderer']['subMenuItems'][1]['continuation']['reloadContinuationData']['continuation']
        except Exception as e:
            # This equality is only there for the purpose of removing an error that is not supposed to exist, it has no purpose otherwise.
            e = e
            print(f"Couldn't find the livestream chat. Is the channel not live? URL: {live_url}.")
            time.sleep(5)
            exit(1)
            

        # Fetch live chat page.
        res = self.session.get(f'https://youtube.com/live_chat?continuation={iframe_continuation}')
        if not res.ok:
            print(f"Couldn't load live chat page ({res.status_code} {res.reason}).")
            time.sleep(5)
            exit(1)
        live_chat_page = res.text

        # Find initial data in live chat page.
        matches = list(self.re_initial_data.finditer(live_chat_page))
        if len(matches) == 0:
            print("Couldn't find initial data in live chat page.")
            time.sleep(5)
            exit(1)
        initial_data = json.loads(matches[0].group(1))

        # Find configuration data.
        matches = list(self.re_config.finditer(live_chat_page))
        if len(matches) == 0:
            print("Couldn't find configuration data in live chat page.")
            time.sleep(5)
            exit(1)
        self.config = json.loads(matches[0].group(1))

        # Create a payload object for making live chat requests.
        token = self.get_continuation_token(initial_data)
        self.payload = {
            "context": self.config['INNERTUBE_CONTEXT'],
            "continuation": token,
            "webClientInfo": {
                "isDocumentHidden": False
            },
        }
        print("Connected.")

    def fetch_messages(self):
        payload_bytes = bytes(json.dumps(self.payload), "utf8")
        res = self.session.post(f"https://www.youtube.com/youtubei/v1/live_chat/get_live_chat?key={self.config['INNERTUBE_API_KEY']}&prettyPrint=false", payload_bytes)
        if not res.ok:
            print(f"Failed to fetch messages ({res.status_code} {res.reason}).")
            print("Body:", res.text, ".")
            print("Payload:", payload_bytes, ".")
            self.session.close()
            self.session = None
            return []
        data = json.loads(res.text)
        self.payload['continuation'] = self.get_continuation_token(data)
        cont = data['continuationContents']['liveChatContinuation']
        messages = []
        if 'actions' in cont:
            for action in cont['actions']:
                if 'addChatItemAction' in action:
                    item = action['addChatItemAction']['item']['liveChatTextMessageRenderer']
                    messages.append({'author': item['authorName']['simpleText'], 'content': item['message']['runs']})
        return messages

    def twitch_receive_messages(self):
        if self.session == None:
            self.reconnect(1)
        messages = []
        if not self.fetch_job:
            time.sleep(1.0/60.0)
            if time.time() > self.next_fetch_time:
                self.fetch_job = self.thread_pool.submit(self.fetch_messages)
        else:
            res = []
            timed_out = False
            try:
                res = self.fetch_job.result(1.0/60.0)
            except concurrent.futures.TimeoutError:
                timed_out = True
            except Exception as e:
                print(e)
                self.session.close()
                self.session = None
                return
            if not timed_out:
                self.fetch_job = None
                self.next_fetch_time = time.time() + YOUTUBE_FETCH_INTERVAL
            for item in res:
                msg = {
                    'username' : item['author'],
                    'message' : ''
                }
                for part in item['content']:
                    if 'text' in part:
                        msg['message'] += part['text']
                    elif 'emoji' in part:
                        msg['message'] += part['emoji']['emojiId']
                messages.append(msg)
        return messages


########################## COMMANDES ##########################



# Replace this with the title of the window you want to use (I'd recommand opening an empty Notepad if you want to test).
WINDOW_TITLE = "WINDOW_TITLE"

# If you don't want commands to be able to be executed multiple times, set this to "False".
COMMANDS_MULTIPLE_TIMES = True

# Replace this with your Twitch username. Must be all lowercase.
TWITCH_CHANNEL = 'TWITCH_CHANNEL' 

# If you're streaming on Youtube, set this to "False".
STREAMING_ON_TWITCH = True

# If you're streaming on Youtube, set this to your channel ID.
# Find it by following this path: YouTube profile picture -> Settings -> Advanced settings.
YOUTUBE_CHANNEL_ID = "YOUTUBE_CHANNEL_ID" 

# If you're using an unlisted stream to test on Youtube, replace "None" below with your stream's URL in quotes. Otherwise leave that to "None".
YOUTUBE_STREAM_URL = None

# "MESSAGE_RATE" controls how fast incoming Twitch chat messages are processed. It's the number of seconds it will take to handle all messages in the queue.
# This is used because Twitch delivers messages in "batches", rather than one at a time. So we process the messages over "MESSAGE_RATE" duration, rather than processing the entire batch at once.
# A smaller number means we go through the message queue faster, but we will run out of messages faster and activity might "stagnate" while waiting for a new batch. 
# A higher number means we go through the queue slower and messages are more evenly spread out, but delay from the viewers' perspective is higher.
# Setting this to 0 disables the queue and handles all messages immediately. However, then the wait before another batch of messages is more noticeable.
MESSAGE_RATE = 0.5

# "MAX_QUEUE_LENGTH" limits the number of commands that will be processed in a given "batch" of messages.
# e.g. If you get a batch of 50 messages, you can choose to only process the first 10 of them and ignore the others.
# This is helpful for games where too many inputs at once can really hinder the gameplay.
# Setting this to ~50 is good when it's the total chaos, ~5-10 is good for 2D platformers.
MAX_QUEUE_LENGTH = 20
MAX_WORKERS = 100 # Maximum number of threads that can be processed at a time.

last_time = time.time()
message_queue = []
thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)
active_tasks = []

if STREAMING_ON_TWITCH:
    t = Twitch()
    t.twitch_connect(TWITCH_CHANNEL)
else:
    t = YouTube()
    t.youtube_connect(YOUTUBE_CHANNEL_ID, YOUTUBE_STREAM_URL)

def handle_message(message):
    try:
        msg = message['message'].lower()
        username = message['username'].lower()

        print(username + ": " + msg)            

        # Now, we've got the message.
        
        # Find the number of time that the command needs to be executed.
        # It's actually limited between 1 and 5, but by adding the digits from 6 to 9, you can put more.
        # On the other hand, this doesn't work with numbers with two digits or more.
        if COMMANDS_MULTIPLE_TIMES:
            if msg[-1] in "12345":
                number_of_times = int(msg[-1])
                msg = msg[:-1]
            else:
                number_of_times = 1
        else:
            number_of_times = 1
        
        # If the message is a command, then execute it the desired number of times.
        # Every part is customizable.
        # Every 'if msg == "[COMMAND]"' allows the program to check if the message is a command. Every command must be put in it, otherwise it will not be executed.
        # Just replace [COMMAND] and [KEY] by the desired command and key.
        if msg == "[COMMAND]":
            print("The message is a command.")      
            # If the command doesn't correspond to the key that needs to be pressed, we need to make sure it becomes the case.
            if msg == "[COMMAND]":
                msg = "[KEY]"
                
            # Connect to an app.
            app = Application(backend="uia").connect(title=WINDOW_TITLE)
                
            # Find the correct window.
            window = app.window(title=WINDOW_TITLE)
               
            # Put the window in focus.
            window.set_focus()
            
            # This part is customizable too, it manages if there are 2 keys (or more) to press at once.
            # Just replace [COMMAND], [KEY1] and [KEY2] by the desired command and keys (and add others if there are any).
            if msg == "[COMMAND]":
                for i in range(number_of_times):
                    pyautogui.keyDown("[KEY1]")
                    pyautogui.keyDown("[KEY2]")
                    time.sleep(0.5)
                    pyautogui.keyUp("[KEY2]")
                    pyautogui.keyUp("[KEY1]")
                print('Keys [KEY1] and [KEY2] sent ' + str(number_of_times) + ' times to the window "' + WINDOW_TITLE + '".')
                    
            else:
                # Send the command to the window.          
                pyautogui.keyDown(msg)
                time.sleep(0.25 * number_of_times)
                pyautogui.keyUp(msg)
                print('Key ' + msg + ' sent ' + str(number_of_times) + ' times to the window "' + WINDOW_TITLE + '".')
            print("Command executed.")
            
        else:
            print("The message is not a command.")
            
    except Exception as e:
        print("Encountered exception: " + str(e) + ".")

while True:
    
    active_tasks = [t for t in active_tasks if not t.done()]

    # Check for new messages.
    new_messages = t.twitch_receive_messages();
    if new_messages:
        message_queue += new_messages; # New messages are added to the back of the queue.
        message_queue = message_queue[-MAX_QUEUE_LENGTH:] # Shorten the queue to only the most recent X messages.

    messages_to_handle = []
    if not message_queue:
        # No messages in the queue.
        last_time = time.time()
    else:
        # Determine how many messages should be handled at the same time.
        r = 1 if MESSAGE_RATE == 0 else (time.time() - last_time) / MESSAGE_RATE
        n = int(r * len(message_queue))
        if n > 0:
            # Pop the messages we want off the front of the queue.
            messages_to_handle = message_queue[0:n]
            del message_queue[0:n]
            last_time = time.time();

    if not messages_to_handle:
        continue
    else:
        for message in messages_to_handle:
            if len(active_tasks) <= MAX_WORKERS:
                active_tasks.append(thread_pool.submit(handle_message, message))
            else:
                print(f'WARNING: active tasks ({len(active_tasks)}) exceeds number of "MAX_WORKERS" ({MAX_WORKERS}). ({len(message_queue)} messages in the queue).')