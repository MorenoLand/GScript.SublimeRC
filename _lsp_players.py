import sublime

def get_player_info(word):
    try:
        from . import _main
        if hasattr(_main, 'GPlugin') and hasattr(_main.GPlugin, 'players'):
            players = _main.GPlugin.players
            word_lower = word.lower()
            matches = []
            for player in players:
                account = player.get('account', '')
                nick = player.get('nickname', account)
                if account.lower() == word_lower or nick.lower() == word_lower:
                    matches.append(player)

            if not matches:
                return None

            player = matches[0]
            account = player.get('account', '')
            nick = player.get('nickname', account)
            player_id = player.get('id', 0)
            level = player.get('level', 'Unknown')

            badges = []
            has_rc = False
            has_player = False
            for p in matches:
                if not p.get('server') and not p.get('external'):
                    has_rc = True
                else:
                    has_player = True

            if has_rc:
                badges.append('RC')
            if has_player:
                badges.append('Player')

            return {
                'account': account,
                'nick': nick,
                'id': player_id,
                'level': level,
                'badges': badges
            }
    except (ImportError, AttributeError):
        pass
    return None

def get_player_completions(prefix):
    completions = []
    try:
        from . import _main
        if hasattr(_main, 'GPlugin') and hasattr(_main.GPlugin, 'players'):
            players = _main.GPlugin.players
            prefix_lower = prefix.lower()
            for player in players:
                account = player.get('account', '')
                nick = player.get('nickname', account)
                level = player.get('level', 'Unknown')
                player_id = player.get('id', 0)
                if account and (account.lower().startswith(prefix_lower) or nick.lower().startswith(prefix_lower)):
                    details = "Nick: {} | ID: {}".format(nick, player_id)
                    completion_item = sublime.CompletionItem.snippet_completion(
                        trigger=account,
                        snippet=account,
                        annotation="RC" if level == "" else "CLIENT",
                        kind=sublime.KIND_AMBIGUOUS,
                        details=details
                    )
                    completions.append(completion_item)
                    if nick and nick != account and nick.lower().startswith(prefix_lower):
                        nick_details = "Nick: {} | Account: {} | ID: {}".format(nick, account, player_id)
                        nick_completion = sublime.CompletionItem.snippet_completion(
                            trigger=nick,
                            snippet=account,
                            annotation="RC" if level == "" else "CLIENT",
                            kind=sublime.KIND_AMBIGUOUS,
                            details=nick_details
                        )
                        completions.append(nick_completion)
    except (ImportError, AttributeError):
        pass
    return completions
