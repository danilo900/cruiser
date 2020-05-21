import logging
import os.path

import requests
import simpleaudio as sa

from bot.protocol import (
    NotifyHostileEvent,
    NotifyFleetRecalled,
    NotifyFleetSaved,
    NotifyExpeditionFinished,
    NotifyExpeditionCancelled,
    NotifyWakeUp,
    NotifySavedFleetRecalled,
    NotifyPlanetsSafe,
    NotifyHostileEventRecalled,
    NotifyStarted,
    NotifyStopped
)
from ogame.util import ftime


class Listener:
    def notify(self, notification): pass
    def notify_exception(self, exception): pass


class TelegramListener(Listener):
    def __init__(self, chat_id, api_token):
        self.chat_id = chat_id
        self.api_token = api_token

    def notify(self, notification):
        message = parse_notification(notification)
        if message:
            message = self._escape_markdown_string(message)
            self._send_message(message, parse_mode='MarkdownV2')

    def notify_exception(self, exception):
        message = parse_exception(exception)
        self._send_message(message)

    def _send_message(self, message, **kwargs):
        try:
            response = requests.get(
                self._send_message_url,
                timeout=5,
                params={'chat_id': self.chat_id, 'text': message, **kwargs})
            response = response.json()
            if not response.get('ok'):
                logging.error(f'Failed to send telegram message: {response.get("description")}')
        except requests.exceptions.RequestException:
            logging.exception('Exception thrown while sending a telegram message.')
        except ValueError:
            logging.exception('Exception thrown while parsing the response.')

    @staticmethod
    def _escape_markdown_string(string):
        for c in '_[]()~>#+-=|{}.!':
            string = string.replace(c, f'\\{c}')
        return string

    @property
    def _send_message_url(self):
        return f'{self._api_url}/sendMessage'

    @property
    def _api_url(self):
        return f'https://api.telegram.org/bot{self.api_token}'


class AlertListener(Listener):
    def __init__(self, wakeup_wav=None, error_wav=None):
        self._check_wav_file(wakeup_wav)
        self._check_wav_file(error_wav)
        self.wakeup_wav = wakeup_wav
        self.error_wav = error_wav

    def notify(self, notification):
        if self.wakeup_wav and isinstance(notification, NotifyWakeUp):
            self._play_async(self.wakeup_wav)

    def notify_exception(self, exception):
        if self.error_wav:
            self._play_async(self.error_wav)

    @staticmethod
    def _play_async(wav_file):
        sa.WaveObject.from_wave_file(wav_file).play()

    @staticmethod
    def _check_wav_file(file):
        if file is not None:
            if not os.path.exists(file):
                raise ValueError(f'Audio file does not exists: {file}')
            if not os.path.isfile(file):
                raise ValueError(f'Path is not a file: {file}')
            _, ext = os.path.splitext(file)
            if ext != '.wav':
                raise ValueError(f'Only wave files (.wav) are supported: {file}')


def parse_notification(notif):
    if isinstance(notif, NotifyHostileEvent):
        if notif.previous_hostile_arrival:
            return f'Hostile fleet attacking `{notif.planet}` delayed from `{ftime(notif.previous_hostile_arrival)}` ' \
                   f'to `{ftime(notif.hostile_arrival)}`.'
        else:
            return f'Hostile fleet attacking `{notif.planet}` on `{ftime(notif.hostile_arrival)}`.'
    elif isinstance(notif, NotifyPlanetsSafe):
        return 'No hostile fleets on sight. Your planets are safe.'
    elif isinstance(notif, NotifyHostileEventRecalled):
        return f'Hostile fleet attacking `{notif.planet}` on `{ftime(notif.hostile_arrival)}` has been recalled.'
    elif isinstance(notif, NotifyFleetSaved):
        if notif.error:
            return f'Failed to save fleet from an attack on `{notif.origin}` ' \
                   f'on `{ftime(notif.hostile_arrival)}`: `{notif.error}`'
        else:
            return f'Fleet escaped from `{notif.origin}` to `{notif.destination}` ' \
                   f'due to an attack on `{ftime(notif.hostile_arrival)}`.'
    elif isinstance(notif, NotifyFleetRecalled):
        if notif.error:
            return f'Failed to recall fleet back to `{notif.origin}` ' \
                   f'due to attack on `{notif.destination}` on `{ftime(notif.hostile_arrival)}`: `{notif.error}`'
        else:
            return f'Recalled fleet back to `{notif.origin}` ' \
                   f'due to attack on `{notif.destination}` on `{ftime(notif.hostile_arrival)}`.'
    elif isinstance(notif, NotifyExpeditionFinished):
        if notif.error:
            return f'Expedition from `{notif.expedition.origin}` had to be removed due to an error: `{notif.error}`'
        else:
            return f'Expedition from `{notif.expedition.origin}` finished successfully.'
    elif isinstance(notif, NotifyExpeditionCancelled):
        if notif.cancellation.return_fleet:
            if notif.fleet_returned:
                return f'Expedition from `{notif.expedition.origin}` has been cancelled and the fleet returned.'
            else:
                return f'Expedition from `{notif.expedition.origin}` has been cancelled' \
                       f'but the fleet could not be returned.'
        else:
            return f'Expedition from `{notif.expedition.origin}` has been cancelled.'
    elif isinstance(notif, NotifySavedFleetRecalled):
        if notif.error:
            return f'Failed to recall fleet escaping from `{notif.origin}`: `{notif.error}`'
        else:
            return f'Fleet escaping from `{notif.origin}` is now successfully recalled.'
    elif isinstance(notif, NotifyStarted):
        return 'Cruiser is active.'
    elif isinstance(notif, NotifyStopped):
        return 'Cruiser is deactivated.'
    elif isinstance(notif, NotifyWakeUp):
        pass  # ignore
    else:
        logging.warning(f'Unknown notification: {notif}')


def parse_exception(e):
    if isinstance(e, requests.Timeout):
        return f'Exception occurred: Connection timed out'
    else:
        return f'Exception occurred: {e}'
