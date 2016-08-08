from unittest.mock import patch

from tests.base import TestCaseWeb, app
from cache import get_cache
from models import Game, User
from helpers import get_prefix, get_queue_name
import consts


class TestHandlerMain(TestCaseWeb):
    url_prefix = '/v1/'

    def test_index(self):
        resp = self.client.get(self.url(''))
        data = self.load_data(resp)
        self.assertTrue(data['rc'])
        self.assertIn('message', data)

    @patch('handlers.main.send_message')
    def test_server_error_1(self, send_message):
        app.config['DEBUG'] = False
        send_message.side_effect = ValueError('value_err')
        with self.assertLogs('app', level='CRITICAL'):
            resp = self.client.get(self.url(''))
            self.assertEqual(resp.status_code, 500)

    @patch('handlers.main.send_message')
    def test_server_error_2(self, send_message):
        app.config['DEBUG'] = True
        send_message.side_effect = ValueError('value_err')
        with self.assertLogs('app', level='CRITICAL'),\
                self.assertRaises(ValueError, msg='value_err'):
            self.client.get(self.url(''))


class TestHandlerAuth(TestCaseWeb):
    url_prefix = '/v1/auth/'

    def test_register_1(self):
        # wrong method
        resp = self.client.get(self.url('register'))
        self.assertEqual(resp.status_code, 405)
        # validator create error
        resp = self.client.post(self.url('register'), data={})
        data = self.load_data(resp)
        self.assertFalse(data['rc'])
        self.assertIn('error', data)
        # validation field error
        resp = self.client.post(self.url('register'), data={
            'username': 'user1',
            'password': ''
        })
        data = self.load_data(resp)
        self.assertFalse(data['rc'])
        self.assertIn('error', data)

    def test_register_2(self):
        # successful registration without email
        with patch('connections.send_mail_template') as mock:
            resp = self.client.post(self.url('register'), data={
                'username': 'user1',
                'password': 'password'
            })
            data = self.load_data(resp)
            self.assertTrue(data['rc'])
            self.assertIn('message', data)
            self.assertFalse(mock.called)

    def test_register_3(self):
        # successful registration with email
        with patch('handlers.auth.send_mail_template') as mock,\
                patch('models.User.get_verification') as mock1:
            mock1.return_value = 'token'
            resp = self.client.post(self.url('register'), data={
                'username': 'user1',
                'password': 'password',
                'email': 'user1@fakemail',
            })
            data = self.load_data(resp)
            self.assertTrue(data['rc'])
            self.assertIn('message', data)
            mock.assert_called_once_with('registration', ['user1@fakemail'], data={
                'username': 'user1',
                'token': 'token'
            })

    def test_login_1(self):
        user_data = {
            'username': 'user1',
            'password': 'password',
        }
        # wrong method
        resp = self.client.get(self.url('login'), data=user_data)
        self.assertEqual(resp.status_code, 405)
        # user not found
        resp = self.client.post(self.url('login'), data=user_data)
        data = self.load_data(resp)
        self.assertFalse(data['rc'])
        self.assertIn('error', data)

    def test_login_2(self):
        # add user and login
        self.add_user('user1', 'password', 'user1@fakemail', 'token')
        user_data = {
            'username': 'user1',
            'password': 'password',
        }
        resp = self.client.post(self.url('login'), data=user_data)
        data = self.load_data(resp)
        self.assertTrue(data['rc'])
        self.assertIn('auth', data)

    def test_logout_1(self):
        # try to logout without login before
        resp = self.client.get(self.url('logout'))
        data = self.load_data(resp)
        self.assertFalse(data['rc'])
        self.assertIn('error', data)

    def test_logout_2(self):
        # login and logout
        auth_token = self.login(*self.add_user('user1', 'password', 'user1@fakemail'))
        self.assertIsNotNone(get_cache(auth_token))
        resp = self.client.get(self.url('logout'))
        data = self.load_data(resp)
        self.assertTrue(data['rc'])
        self.assertIn('message', data)
        self.assertIsNone(get_cache(auth_token))

    def test_get_verification_1(self):
        # try to get verification token without login before
        resp = self.client.get(self.url('verification'))
        data = self.load_data(resp)
        self.assertFalse(data['rc'])
        self.assertIn('error', data)

    def test_get_verification_2(self):
        # login and get verification token
        self.login(*self.add_user('user1', 'password', 'user1@fakemail'))
        with patch('handlers.auth.send_mail_template') as mock,\
                patch('models.User.get_verification') as mock1:
            mock1.return_value = 'token'
            resp = self.client.get(self.url('verification'))
            mock.assert_called_once_with('verification', ['user1@fakemail'], data={
                'username': 'user1',
                'token': 'token',
            })
        self.assertTrue(self.load_data(resp)['rc'])

    def test_verify_1(self):
        # try to verificate with wrong token
        resp = self.client.get(self.url('verification/token'))
        data = self.load_data(resp)
        self.assertFalse(data['rc'])
        self.assertIn('error', data)

    def test_verify_2(self):
        # login, get verification token and verify
        self.login(*self.add_user('user1', 'password', 'user1@fakemail'))
        with patch('models.generate_token') as mock:
            mock.return_value = 'token'
            resp = self.client.get(self.url('verification'))
        resp = self.client.get(self.url('verification/token'))
        self.assertTrue(self.load_data(resp)['rc'])

    def test_reset_1(self):
        self.add_user('user1', 'password', 'user1@fakemail')
        resp = self.client.post(self.url('reset'), data={'email': 'user1'})
        data = self.load_data(resp)
        self.assertFalse(data['rc'])
        self.assertIn('error', data)

    def test_reset_2(self):
        self.add_user('user1', 'password', 'user1@fakemail')
        resp = self.client.post(self.url('reset'), data={'email': 'user2@fakemail'})
        data = self.load_data(resp)
        self.assertFalse(data['rc'])
        self.assertIn('error', data)

    def test_recover_1(self):
        self.add_user('user1', 'passwd', 'user1@fakemail')
        resp = self.client.post(self.url('recover/token'), data={'password': 'pass'})
        data = self.load_data(resp)
        self.assertFalse(data['rc'])
        self.assertIn('error', data)

    def test_recover_2(self):
        self.add_user('user1', 'passwd', 'user1@fakemail')
        resp = self.client.post(self.url('recover/token'), data={'password': 'password'})
        data = self.load_data(resp)
        self.assertFalse(data['rc'])
        self.assertIn('error', data)

    def test_reset_and_recover(self):
        self.add_user('user1', 'password', 'user1@fakemail')
        with patch('handlers.auth.send_mail_template') as mock,\
                patch('models.generate_token') as mock1:
            mock1.return_value = 'token'
            resp = self.client.post(self.url('reset'), data={'email': 'user1@fakemail'})
            mock.assert_called_once_with('reset', ['user1@fakemail'], data={
                'username': 'user1',
                'token': 'token',
            })
            self.assertTrue(self.load_data(resp)['rc'])
        resp = self.client.post(self.url('recover/token'), data={'password': 'password'})
        self.assertTrue(self.load_data(resp)['rc'])
        self.assertTrue(User.authenticate('user1', 'password'))


class TestHandlerGame(TestCaseWeb):
    url_prefix = '/v1/game/'

    def new_game(self, game_type=None, game_limit=None):
        game_data = {
            'type': game_type,
            'limit': game_limit,
        }
        resp = self.client.post(self.url('new'), data=game_data)
        token1 = self.load_data(resp)['game']
        resp = self.client.post(self.url('new'), data=game_data)
        token2 = self.load_data(resp)['game']
        return token1, token2

    def test_types(self):
        resp = self.client.get(self.url('types'))
        data = self.load_data(resp)
        self.assertIn('no limit', data['types'])
        self.assertIn('slow', data['types'])
        self.assertIn('fast', data['types'])

    def test_new_game_1(self):
        # wrong method
        resp = self.client.get(self.url('new'))
        self.assertEqual(resp.status_code, 405)
        # validator create error
        game_data = {'type': 'err_type'}
        resp = self.client.post(self.url('new'), data=game_data)
        data = self.load_data(resp)
        self.assertFalse(data['rc'])
        self.assertIn('error', data)
        # validation field error
        game_data = {'type': 'slow', 'limit': 'err_limit'}
        resp = self.client.post(self.url('new'), data=game_data)
        data = self.load_data(resp)
        self.assertFalse(data['rc'])
        self.assertIn('error', data)

    def test_new_game_2(self):
        # two requests with the same type and limit, start game
        game_data = {'type': 'slow', 'limit': '1d'}
        # send first request
        resp = self.client.post(self.url('new'), data=game_data)
        data = self.load_data(resp)
        user1_token = data['game']
        expect = {'rc': True, 'game': {}}
        self.assertComprateDicts(data, expect)
        # send second request
        resp = self.client.post(self.url('new'), data=game_data)
        data = self.load_data(resp)
        user2_token = data['game']
        expect = {
            'rc': True, 'board': {}, 'time_left': {}, 'enemy_time_left': {}, 
            'started_at': {}, 'ended_at': None, 'game': {}, 'next_turn': 'white'
        }
        self.assertComprateDicts(data, expect)
        # check game and cache
        game = Game.get()
        self.assertIsNone(game.player_white)
        self.assertIsNone(game.player_black)
        self.assertEqual(get_cache(user1_token), (game.pk, consts.WHITE, user2_token))
        self.assertEqual(get_cache(user2_token), (game.pk, consts.BLACK, user1_token))

    def test_new_game_3(self):
        # case 2 with login
        self.login(*self.add_user('user1', 'password', None))
        self.client.post(self.url('new'), data={})
        self.login(*self.add_user('user2', 'password', None))
        self.client.post(self.url('new'), data={})
        game = Game.get()
        self.assertIsInstance(game.player_white, User)
        self.assertIsInstance(game.player_black, User)

    def test_new_game_4(self):
        # two requests: first has limit, second not, start game
        game_data = {'type': 'slow', 'limit': '1d'}
        self.client.post(self.url('new'), data=game_data)
        resp = self.client.post(self.url('new'), data={'type': 'slow'})
        data = self.load_data(resp)
        expect = {
            'rc': True, 'board': {}, 'time_left': {}, 'enemy_time_left': {}, 
            'started_at': {}, 'ended_at': None, 'game': {}, 'next_turn': 'white'
        }
        self.assertComprateDicts(data, expect)

    def test_new_game_5(self):
        # two requests: second has limit, first not, start game
        self.client.post(self.url('new'), data={'type': 'slow'})
        game_data = {'type': 'slow', 'limit': '1d'}
        resp = self.client.post(self.url('new'), data=game_data)
        data = self.load_data(resp)
        expect = {
            'rc': True, 'board': {}, 'time_left': {}, 'enemy_time_left': {}, 
            'started_at': {}, 'ended_at': None, 'game': {}, 'next_turn': 'white'
        }
        self.assertComprateDicts(data, expect)

    def test_new_game_6(self):
        # two requests without limit, not start game
        self.client.post(self.url('new'), data={'type': 'slow'})
        resp = self.client.post(self.url('new'), data={'type': 'slow'})
        data = self.load_data(resp)
        expect = {'rc': True, 'game': {}}
        self.assertComprateDicts(data, expect)

    def test_new_game_7(self):
        # one user starts game twice, only last should stay
        name = get_queue_name(get_prefix(consts.TYPE_NOLIMIT))
        self.login(*self.add_user('user1', 'password', None))
        resp = self.client.post(self.url('new'), data={})
        data = self.load_data(resp)
        self.assertTrue(data['rc'])
        token1 = data['game']
        self.assertIn(token1, get_cache(name).decode())
        resp = self.client.post(self.url('new'), data={})
        data = self.load_data(resp)
        self.assertTrue(data['rc'])
        token2 = data['game']
        self.assertNotIn(token1, get_cache(name).decode())
        self.assertIn(token2, get_cache(name).decode())

    def test_invite_1(self):
        resp = self.client.post(self.url('invite'), data={'type': 'slow'})
        self.assertFalse(self.load_data(resp)['rc'])

    def test_invite_2(self):
        # create invitation
        resp = self.client.post(self.url('invite'), data={'type': 'no limit'})
        data = self.load_data(resp)
        expect = {'rc': True, 'game': {}, 'invite': {}}
        self.assertComprateDicts(data, expect)
        token = data['invite']
        # start game with invitation token
        resp = self.client.get(self.url('invite/{}'.format(token)))
        data = self.load_data(resp)
        expect = {
            'rc': True, 'board': {}, 'time_left': {}, 'enemy_time_left': {}, 
            'started_at': {}, 'ended_at': None, 'game': {}, 'next_turn': 'white'
        }
        self.assertComprateDicts(data, expect)

    def test_invite_3(self):
        resp = self.client.get(self.url('invite/token'), data={'type': 'slow'})
        self.assertFalse(self.load_data(resp)['rc'])

    def test_active(self):
        # create user1 and invite
        self.login(*self.add_user('user1', 'password', None))
        resp = self.client.post(self.url('invite'), data={'type': 'no limit'})
        data = self.load_data(resp)
        game1_w = data['game']
        # create user2, accept invite and invite again
        self.login(*self.add_user('user2', 'password', None))
        resp = self.client.get(self.url('invite/{}'.format(data['invite'])))
        game1_b = self.load_data(resp)['game']
        resp = self.client.post(self.url('invite'), data={'type': 'no limit'})
        data = self.load_data(resp)
        game2_w = data['game']
        # check games of user2
        resp = self.client.get(self.url('active'))
        self.assertEqual(self.load_data(resp), {'rc': True, 'games': [game1_b]})
        # login as user1, accept invite and check games
        self.login('user1', 'password')
        resp = self.client.get(self.url('invite/{}'.format(data['invite'])))
        game2_b = self.load_data(resp)['game']
        resp = self.client.get(self.url('active'))
        self.assertEqual(self.load_data(resp), {'rc': True, 'games': [game1_w, game2_b]})

    def test_game_info(self):
        user_token1, user_token2 = self.new_game()
        # test first token
        resp = self.client.get(self.url('{}/info'.format(user_token1)))
        data = self.load_data(resp)
        expect = {
            'rc': True, 'started_at': {}, 'ended_at': None, 'board': {},
            'time_left': {}, 'enemy_time_left': {}, 'next_turn': 'white',
        }
        self.assertComprateDicts(data, expect)
        # test second token
        resp = self.client.get(self.url('{}/info'.format(user_token2)))
        data = self.load_data(resp)
        expect = {
            'rc': True, 'started_at': {}, 'ended_at': None, 'board': {},
            'time_left': {}, 'enemy_time_left': {}, 'next_turn': 'white',
        }
        self.assertComprateDicts(data, expect)

    def test_game_move_1(self):
        user_token1, user_token2 = self.new_game()
        # wrong method
        resp = self.client.get(self.url('token/move'))
        self.assertEqual(resp.status_code, 405)
        # validator create error
        resp = self.client.post(self.url('{}/move'.format(user_token1)), data={})
        data = self.load_data(resp)
        self.assertFalse(data['rc'])
        self.assertIn('error', data)
        # validation field error
        move_data = {'move': 'e0-e1'}
        resp = self.client.post(self.url('{}/move'.format(user_token2)), data=move_data)
        data = self.load_data(resp)
        self.assertFalse(data['rc'])
        self.assertIn('error', data)

    def test_game_move_2(self):
        user_token1, user_token2 = self.new_game()
        move_data = {'move': 'e2-e4'}
        resp = self.client.post(self.url('{}/move'.format(user_token1)), data=move_data)
        data = self.load_data(resp)
        expect = {
            'rc': True, 'started_at': {}, 'ended_at': None, 'board': {},
            'time_left': {}, 'enemy_time_left': {}, 'next_turn': 'black',
        }
        self.assertComprateDicts(data, expect)

    def test_draw_accept(self):
        user_token1, user_token2 = self.new_game()
        # draw request and accept after, game is over
        resp = self.client.get(self.url('{}/draw/accept'.format(user_token1)))
        self.assertEqual(self.load_data(resp), {'rc': True})
        resp = self.client.get(self.url('{}/draw/accept'.format(user_token2)))
        data = self.load_data(resp)
        expect = {'rc': True, 'message': {}}
        self.assertComprateDicts(data, expect)

    def test_draw_refuse_1(self):
        user_token1, user_token2 = self.new_game()
        # draw request and refuse after by second player, game is not over
        resp = self.client.get(self.url('{}/draw/accept'.format(user_token1)))
        self.assertEqual(self.load_data(resp), {'rc': True})
        resp = self.client.get(self.url('{}/draw/refuse'.format(user_token2)))
        self.assertEqual(self.load_data(resp), {'rc': True})
        # draw request from second player, game is not over
        resp = self.client.get(self.url('{}/draw/accept'.format(user_token2)))
        self.assertEqual(self.load_data(resp), {'rc': True})

    def test_draw_refuse_2(self):
        user_token1, user_token2 = self.new_game()
        # draw request and refuse after by first player, game is not over
        resp = self.client.get(self.url('{}/draw/accept'.format(user_token1)))
        self.assertEqual(self.load_data(resp), {'rc': True})
        resp = self.client.get(self.url('{}/draw/refuse'.format(user_token1)))
        self.assertEqual(self.load_data(resp), {'rc': True})
        # draw request from second player, game is not over
        resp = self.client.get(self.url('{}/draw/accept'.format(user_token2)))
        self.assertEqual(self.load_data(resp), {'rc': True})

    def test_resign(self):
        user_token1, user_token2 = self.new_game()
        # resign game
        resp = self.client.get(self.url('{}/resign'.format(user_token1)))
        self.assertEqual(self.load_data(resp), {'rc': True})
        # try to resign ended game
        resp = self.client.get(self.url('{}/resign'.format(user_token2)))
        data = self.load_data(resp)
        self.assertFalse(data['rc'])
        self.assertIn('error', data)

    def test_moves(self):
        user_token1, user_token2 = self.new_game()
        resp = self.client.get(self.url('{}/moves'.format(user_token1)))
        self.assertEqual(self.load_data(resp), {'rc': True, 'moves': []})
