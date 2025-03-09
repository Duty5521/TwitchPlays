# Salut ! Duty qui parle ! Ce programme qui laisse jouer Twitch (et YouTube si besoin) est basé sur celui de DougDoug que j'ai traduit et adapté selon mes besoins !
# Il n'est probablement pas le plus optimisé et le plus simple à comprendre/mettre en place, mais il marche très bien.
# Je recommenderais vraiment de ne changer aucune valeur (à part celles qui sont faites pour), ça marche très bien avec celles actuelles.
# Sur ce, bon live et bonne chance au chat !


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


########################## CONNEXION ##########################
# Note de DougDoug: 
# Ceci est la partie du code qui connecte à Twitch/YouTube et regarde si il y a des nouveaux messages.
# Il n'y a normalement besoin de rien modifier dans cette partie, on peut l'utiliser comme c'est.
# Cette partie du code est basée sur le tutoriel "Twitch Plays" de Wituz, mis à jour (c'est Duty qui parle dans cette parenthèse - pour Python 3.9.XX à la base mais je l'ai encore mis à jour pour Python 3.13.XX).
# http://www.wituz.com/make-your-own-twitch-plays-stream.html (ce lien est mort).
# Mis à jour pour YouTube par DDarknut, avec de l'aide de Ottomated.


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

        # Compiler certaines expressions courantes.
        self.re_prog = re.compile(b'^(?::(?:([^ !\r\n]+)![^ \r\n]*|[^ \r\n]*) )?([^ \r\n]+)(?: ([^:\r\n]*))?(?: :([^\r\n]*))?\r\n', re.MULTILINE)

        # Création du point d'accès.
        print('Connexion à Twitch...')
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Essai pour se connecter au point d'accès.
        self.sock.connect(('irc.chat.twitch.tv', 6667))

        # Se connecter anonymement.
        user = 'justinfan%i' % random.randint(10000, 99999)
        print('Connecté à Twitch. Connexion anonyme...')
        self.sock.send(('PASS asdf\r\nNICK %s\r\n' % user).encode())

        self.sock.settimeout(1.0/60.0)

        self.login_timestamp = time.time()

    # Essai pour se reconnecter après un délai.
    def reconnect(self, delay):
        time.sleep(delay)
        self.twitch_connect(self.channel)

    # Renvoie une liste de messages irc reçus.
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
            #         # Cette "erreur" est attendue - elle est reçue si le temps mort est mis à zéro et qu'il n'y a aucune donnée sur le point d'accès.
            #         break
            except Exception as e:
                print('Erreur de connexion innatendue. Reconnexion dans une seconde...', e)
                self.reconnect(1)
                return []
            if not received:
                print('Connexion fermée par Twitch. Reconnexion dans 5 secondes...')
                self.reconnect(5)
                return []
            buffer += received

        if buffer:
            # Ajouter un élément de donnée non analysée des itérations précédentes.
            if self.partial:
                buffer = self.partial + buffer
                self.partial = 0


            # Analyser les messages irc.
            res = []
            matches = list(self.re_prog.finditer(buffer))
            for match in matches:
                res.append({
                    'name':     (match.group(1) or b'').decode(errors='replace'),
                    'command':  (match.group(2) or b'').decode(errors='replace'),
                    'params':   list(map(lambda p: p.decode(errors='replace'), (match.group(3) or b'').split(b' '))),
                    'trailing': (match.group(4) or b'').decode(errors='replace'),
                })

            # Sauvegarder des données qui n'ont pas pu être analysées pour la prochaine itération.
                self.partial + buffer == buffer
            else:
                end = matches[-1].end()
                if end < len(buffer):
                    self.partial = buffer[end:]

                if matches[0].start() != 0:
                    # Si on en est ici, un message a peut-être été raté.
                    print('Un message a peut-être été oublié.')

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
                print('Connexion réussie. En train de rejoindre la chaîne ' + self.channel + '.')
                self.sock.send(('JOIN #%s\r\n' % self.channel).encode())
                self.login_ok = True
            elif cmd == 'JOIN':
                print('Chaîne ' + self.channel + ' rejointe avec succès.')
                # Regarde si la fenêtre précisée en bas existe, si non imprime la liste des fenêtres.
                def window_exists(WINDOW_TITLE):
                    try:
                        app = Application(backend="uia").connect(title=WINDOW_TITLE)
                        app.window(title=WINDOW_TITLE)
                        return True
                    except ElementNotFoundError:
                        return False
                    except Exception as e:
                        print(f"Erreur inattendue : {e}")
                        return False
                if not window_exists(WINDOW_TITLE):
                    print('Fenêtre avec le titre "' + WINDOW_TITLE + '" non trouvée. Liste de toutes les fenêtres : ' + str([w.window_text() for w in Desktop(backend="uia").windows()]) + '.')
                    exit()
            elif cmd == 'NOTICE':
                print('Annonce du serveur :', irc_message['params'], irc_message['trailing'], ".")
            elif cmd == '002': continue
            elif cmd == '003': continue
            elif cmd == '004': continue
            elif cmd == '375': continue
            elif cmd == '372': continue
            elif cmd == '376': continue
            elif cmd == '353': continue
            elif cmd == '366': continue
            else:
                print('Message irc non géré : ', irc_message, ".")

        if not self.login_ok:
            # Le programme est toujours en train d'attendre le message de connexion initial. Si il attend plus longtemps que ce qu'il devrait, il essaiera de se reconnecter.
            if time.time() - self.login_timestamp > MAX_TIME_TO_WAIT_FOR_LOGIN:
                print('Pas de réponse de Twitch. Reconnexion...')
                self.reconnect(0)
                return []

        return privmsgs

# Merci à Ottomated d'avoir aidé avec le côté YouTube du programme !
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
                print("En train d'attendre la fin de la récupération...")
                self.fetch_job.result()
        print(f"Nouvelle tentative dans {delay}...")
        if self.session: self.session.close()
        self.session = None
        self.config = {}
        self.payload = {}
        self.fetch_job = None
        self.next_fetch_time = 0
        time.sleep(delay)
        self.youtube_connect(self.channel_id, self.stream_url)

    def youtube_connect(self, channel_id, stream_url=None):
        print("Connexion à YouTube...")

        self.channel_id = channel_id
        self.stream_url = stream_url

        # Créer une séance http du client.
        self.session = requests.Session()
        # Spoof l'agent utilisateur pour que YouTube pense que c'est un navigateur.
        self.session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Safari/537.36'
        # Ajouter des cookies de consentement pour contourner la page de consentement de Google
        requests.utils.add_dict_to_cookiejar(self.session.cookies, {'CONSENT': 'YES+'})

        # Se connecter en utilisant "stream_url" si fourni, sinon utiliser "channel_id".
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
                print(f"Impossible de charger l'URL du live ({res.status_code} {res.reason}). L'URL de la chaîne ({self.stream_url}) est-il correct ?")
            else:
                print(f"Impossible de charger la page du live ({res.status_code} {res.reason}). L'ID de la chaîne ({self.channel_id}) est-elle correcte ?")
            time.sleep(5)
            exit(1)
        livestream_page = res.text

        # Trouver les données initiales dans la page du live.
        matches = list(self.re_initial_data.finditer(livestream_page))
        if len(matches) == 0:
            print("Impossible de trouver les données initiales dans la page du live.")
            time.sleep(5)
            exit(1)
        initial_data = json.loads(matches[0].group(1))

        # Prendre le token de continuation pour l'iframe du chat du live.
        iframe_continuation = None
        try:
            iframe_continuation = initial_data['contents']['twoColumnWatchNextResults']['conversationBar']['liveChatRenderer']['header']['liveChatHeaderRenderer']['viewSelector']['sortFilterSubMenuRenderer']['subMenuItems'][1]['continuation']['reloadContinuationData']['continuation']
        except Exception as e:
            # Cette égalité est uniquement là dans le but d'enlever une erreur qui n'est pas sensée exister, ça n'a aucun intérêt sinon.
            e = e
            print(f"Impossible de trouver la page de chat du live. La chaîne est-elle hors-live ? URL : {live_url}.")
            time.sleep(5)
            exit(1)
            

        # Analyse la page de chat du live.
        res = self.session.get(f'https://youtube.com/live_chat?continuation={iframe_continuation}')
        if not res.ok:
            print(f"Impossible de charger la page du live ({res.status_code} {res.reason}).")
            time.sleep(5)
            exit(1)
        live_chat_page = res.text

        # Trouver les données initiales dans la page de chat du live.
        matches = list(self.re_initial_data.finditer(live_chat_page))
        if len(matches) == 0:
            print("Impossible de trouver les données initiales dans la page de chat du live.")
            time.sleep(5)
            exit(1)
        initial_data = json.loads(matches[0].group(1))

        # Trouver les données de configuration.
        matches = list(self.re_config.finditer(live_chat_page))
        if len(matches) == 0:
            print("Impossible de trouver les données de configuration dans la page de chat du live.")
            time.sleep(5)
            exit(1)
        self.config = json.loads(matches[0].group(1))

        # Créer un "payload object" pour émettre de demandes de chat.
        token = self.get_continuation_token(initial_data)
        self.payload = {
            "context": self.config['INNERTUBE_CONTEXT'],
            "continuation": token,
            "webClientInfo": {
                "isDocumentHidden": False
            },
        }
        print("Connecté.")

    def fetch_messages(self):
        payload_bytes = bytes(json.dumps(self.payload), "utf8")
        res = self.session.post(f"https://www.youtube.com/youtubei/v1/live_chat/get_live_chat?key={self.config['INNERTUBE_API_KEY']}&prettyPrint=false", payload_bytes)
        if not res.ok:
            print(f"N'a pas réussi à analyser les messages ({res.status_code} {res.reason}).")
            print("Corps :", res.text, ".")
            print("Payload :", payload_bytes, ".")
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



# Remplace ça par le titre de la fenêtre que tu veux utiliser (je recommande d'ouvrir un bloc-notes vide si tu veux tester).
WINDOW_TITLE = "WINDOW_TITLE"

# Si tu ne souhaites pas que les commandes puissent être exécutées plusieurs fois, met ça sur "False".
COMMANDS_MULTIPLE_TIMES = True

# Remplace ça par ton pseudonyme Twitch, tout en minuscule.
TWITCH_CHANNEL = 'TWITCH_CHANNEL' 

# Si tu stream sur YouTube, met ça sur "False".
STREAMING_ON_TWITCH = True

# Si tu stream sur YouTube, remplace ça par ton ID de chaîne.
# Trouve ça en suivant ce chemin : Photo de profil YouTube -> Paramètres -> Paramètres avancés.
YOUTUBE_CHANNEL_ID = "YOUTUBE_CHANNEL_ID" 

# Si tu utilises un stream en non répertorié pour tester sur YouTube, remplace "None" en dessous avec l'URL de ton stream entre guillemets. Sinon laisse ça à "None".
YOUTUBE_STREAM_URL = None

# "MESSAGE_RATE" contrôle à quelle vitesse les messages du chat Twitch sont traités. C'est le nombre de secondes que ça va prendre pour prendre en charge tous les messages dans la file.
# C'est utilisé parce que Twitch livre les messages en gros groupes, plutôt qu'un seul à la fois. Donc on traite les messages sur la durée de "MESSAGE_RATE", plutôt que d'en traiter l'intégralité en une fois.
# Un plus petit nombre veut dire qu'on prend en charge les messages dans la file plus vite mais on va manquer de messages plus vite et l'activité peut "stagner" en attendant des nouveaux messages. 
# Un plus grand nombre veut dire qu'on prend en charge les messages dans la file plus lentement, et les messages sont étalés plus uniformément, mais le délai de la perspecive des spectateurs est plus grande.
# Mettre ça à 0 désactive la file et prend en charge tous les messages immédiatement. Par contre, l'attente avant d'autres messages sera plus visible.
MESSAGE_RATE = 0.5

# "MAX_QUEUE_LENGTH" limite le nombre de commandes qui vont être traitées dans un groupe de messages donné.
# Ex. Si tu as un groupe de 50 messages, tu peux choisir de seulement traiter les 10 premiers et ignorer les autres.
# C'est utile pour les jeux où trop de commandes à la fois peuvent vraiment entraver le gameplay.
# Mettre ça à ~50 est bien quand c'est le chaos total, ~5-10 est bien pour les platformers 2D.
MAX_QUEUE_LENGTH = 20
MAX_WORKERS = 100 # Nombre maximum de fils que l'on peut suivre à la fois.

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

        print(username + " : " + msg)            

        # Maintenant, on a le message.
        
        # Trouver le nombre de fois qu'il faut exécuter la commande.
        # C'est actuellement limité entre 1 et 5, mais en ajoutant les chiffre de 6 à 9 on peut en mettre plus.
        # Par contre cela ne marche pas avec les nombres à deux chiffres ou plus.
        if COMMANDS_MULTIPLE_TIMES:
            if msg[-1] in "12345":
                number_of_times = int(msg[-1])
                msg = msg[:-1]
            else:
                number_of_times = 1
        else:
            number_of_times = 1
        
        # Si le message est une commande, alors l'exécuter le nombre de fois voulu.
        # Cette partie est personnalisable.
        # Chaque 'if msg == "[COMMANDE]"' permet au programme de vérifier si le message est une commande. Chaque commande doit être absolument mise dedans, sinon elle ne sera pas exécutée.
        # Il suffit de remplacer [COMMANDE] et [TOUCHE] par la commande et la touche souhaitées.
        if msg == "[COMMANDE]":
            print("Le message est une commande.")      
            # Si la commande ne correspond pas à la touche qu'il faut appuyer, il faut faire en sorte que ça devienne le cas.
            if msg == "[COMMANDE]":
                msg = "[TOUCHE]"
                
            # Se connecter à une application.
            app = Application(backend="uia").connect(title=WINDOW_TITLE)
                
            # Trouver la bonne fenêtre.
            window = app.window(title=WINDOW_TITLE)
               
            # Mettre la fenêtre en focus.
            window.set_focus()
            
            # Cette partie est personnalisable aussi, elle gère si il y a 2 touches (ou plus) à appuyer à la fois.
            # Il suffit de remplacer [COMMANDE], [TOUCHE1] et [TOUCHE2] par la commande et les touches souhaitées (et en rajouter d'autres si il y en a).
            if msg == "[COMMANDE]":
                for i in range(number_of_times):
                    pyautogui.keyDown("[TOUCHE1]")
                    pyautogui.keyDown("[TOUCHE2]")
                    time.sleep(0.5)
                    pyautogui.keyUp("[TOUCHE2]")
                    pyautogui.keyUp("[TOUCHE1]")
                print('Touches [TOUCHE1] et [TOUCHE2] envoyées ' + str(number_of_times) + ' fois à la fenêtre "' + WINDOW_TITLE + '".')
                    
            else:
                # Envoyer la commande à la fenêtre.          
                pyautogui.keyDown(msg)
                time.sleep(0.25 * number_of_times)
                pyautogui.keyUp(msg)
                print('Touche ' + msg + ' envoyée ' + str(number_of_times) + ' fois à la fenêtre "' + WINDOW_TITLE + '".')
            print("Commande exécutée.")
            
        else:
            print("Le message n'est pas une commande.")
            
    except Exception as e:
        print("Exception rencontrée : " + str(e) + ".")

while True:
    
    active_tasks = [t for t in active_tasks if not t.done()]

    # Regarder si il y a des nouveaux messages.
    new_messages = t.twitch_receive_messages();
    if new_messages:
        message_queue += new_messages; # Les nouveaux messages sont ajoutés à la fin de la queue.
        message_queue = message_queue[-MAX_QUEUE_LENGTH:] # Raccourcir la queue à uniquement les X messages les plus récents.

    messages_to_handle = []
    if not message_queue:
        # Pas de message dans la file.
        last_time = time.time()
    else:
        # Déterminer combien de message devraient être gérés en même temps.
        r = 1 if MESSAGE_RATE == 0 else (time.time() - last_time) / MESSAGE_RATE
        n = int(r * len(message_queue))
        if n > 0:
            # Mettre les messages qui doivent l'être au début de la file.
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
                print(f'ATTENTION : le nombre de tâches actives ({len(active_tasks)}) dépasse le nombre de "MAX_WORKERS" ({MAX_WORKERS}). ({len(message_queue)} messages dans la file).')
