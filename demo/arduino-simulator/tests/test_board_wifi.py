import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from board_wifi import BoardWifi

class BoardWifiTests(unittest.TestCase):
    def test_connection_requires_only_private_ip_for_new_firmware(self):
        board = BoardWifi()
        with patch.object(board, '_request', return_value={'board':'UNO R4 WiFi','protocol':3,'boot':'a','cursor':0}):
            board.connect('192.168.4.1')
        self.assertEqual(board.token, '')
        self.assertEqual(board.host, '192.168.4.1')
    def test_private_ip_and_token_validation_precedes_network(self):
        board=BoardWifi()
        for host in ['127.0.0.1','169.254.169.254','8.8.8.8','localhost','192.168.1.2/path','::1',None]:
            with self.subTest(host=host), self.assertRaises(ValueError):board.connect(host,'x'*32)
        for token in ['short','x'*20+'\r\nInjected:yes',None]:
            with self.assertRaises(ValueError):board.connect('192.168.4.1',token)

    def test_new_connection_discards_history_and_restart_requires_reconnect(self):
        board=BoardWifi()
        with patch.object(board,'_request',return_value={'board':'UNO R4 WiFi','protocol':3,'boot':'a','cursor':50}):
            board.connect('192.168.4.1','x'*32)
        with patch.object(board,'_request',return_value={'boot':'a','cursor':51,'reset':False,'events':[{'id':51,'line':'BUTTON_LAB_KEY:1'}]}) as request:
            self.assertEqual(len(board.poll()['events']),1)
            request.assert_called_once_with('GET','/events?after=50')
        with patch.object(board,'_request',return_value={'boot':'b','cursor':0,'reset':True,'events':[]}):
            with self.assertRaises(ValueError):board.poll()
        self.assertEqual(board.host,'')

    def test_commands_are_single_line_and_never_retried(self):
        board=BoardWifi();board.host='192.168.4.1'
        for command in ['key:1\nkey:2','', 'x'*256,None]:
            with self.assertRaises(ValueError):board.command(command)
        with patch.object(board,'_request',side_effect=ValueError('disconnected')) as request:
            with self.assertRaises(ValueError):board.command('audio:volume:10')
            self.assertEqual(request.call_count,1)

if __name__=='__main__':unittest.main()
