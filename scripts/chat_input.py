"""Portable multiline terminal input without optional dependencies."""


def read_message(multiline=False):
    """Read one complete message; slash commands remain single-line commands.

    /paste enters block input. /send submits and /cancel discards the block.
    EOF discards an unfinished block instead of accidentally sending it.
    """
    first = input('\n你> ')
    if first.strip().startswith('/') and first.strip() != '/paste':
        return first.strip()
    if not multiline and first.strip() != '/paste':
        return first.strip()
    lines = [] if first.strip() == '/paste' else [first]
    print('多行输入：回车换行，单独输入 /send 发送，/cancel 取消。')
    while True:
        line = input('…> ')
        if line.strip() == '/send':
            return '\n'.join(lines).strip()
        if line.strip() == '/cancel':
            return ''
        lines.append(line)
