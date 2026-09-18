"""noteの連載の新しい回を、ホームページのカードの並びに足す。

GitHub Actions から1時間おきに呼ばれる（.github/workflows/update-series.yml）。
手元で試すときは次のように呼ぶ。--file で別のファイルを直せる。

    python tools/update_series.py
    python tools/update_series.py --file 試しの写し.html

決まり
- 連載の回は、題名が「第N回」で始まる記事だけ。ほかの記事は並べない
- 取れなかったとき、取れた数が少ないときは、今あるカードを消さない（足すだけ）
- 何も変わらなければファイルに触らない
"""
import argparse
import datetime as dt
import email.utils
import io
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

CREATOR = 'papaiapain'
UA = {'User-Agent': 'Mozilla/5.0 (papaiapain.github.io series updater)'}
JST = dt.timezone(dt.timedelta(hours=9))
NUM = re.compile(r'^\s*第\s*(\d+)\s*回')


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read()


def from_api():
    found = {}
    for page in range(1, 20):
        d = json.loads(get(f'https://note.com/api/v2/creators/{CREATOR}/contents?kind=note&page={page}'))['data']
        for n in d.get('contents') or []:
            m = NUM.match(n.get('name') or '')
            if m and n.get('key'):
                when = dt.datetime.fromisoformat(n['publishAt']).astimezone(JST) if n.get('publishAt') else None
                found[int(m.group(1))] = (n['key'], when)
        if d.get('isLastPage', True):
            break
    return found


def from_rss():
    found = {}
    root = ET.fromstring(get(f'https://note.com/{CREATOR}/rss'))
    for item in root.iter('item'):
        m = NUM.match(item.findtext('title') or '')
        key = re.search(r'/n/(n[0-9a-z]+)', item.findtext('link') or '')
        if m and key:
            pub = item.findtext('pubDate')
            when = email.utils.parsedate_to_datetime(pub).astimezone(JST) if pub else None
            found[int(m.group(1))] = (key.group(1), when)
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default='index.html')
    path = ap.parse_args().file

    raw = io.open(path, encoding='utf-8', newline='').read()
    nl = '\r\n' if '\r\n' in raw else '\n'
    html = raw.replace('\r\n', '\n')

    start, end = '      <!-- series:start -->\n', '      <!-- series:end -->\n'
    if html.count(start) != 1 or html.count(end) != 1:
        print('カードの並びの目印が見つからないので何もしない')
        return
    head, rest = html.split(start)
    block, tail = rest.split(end)

    # 今あるカード（番号 → 記事の鍵）
    cards = {int(n): k for k, n in re.findall(r'embed/notes/(n[0-9a-z]+)" title="noteの記事 第(\d+)回"', block)}

    fetched = {}
    for name, fn in (('API', from_api), ('RSS', from_rss)):
        try:
            fetched = fn()
            if fetched:
                print(f'noteから{name}で{len(fetched)}回分を取った')
                break
        except Exception as e:  # 取れなくても今のページは壊さない
            print(f'noteの{name}が読めない: {e}')
    if not fetched:
        print('noteから何も取れなかったので何もしない')
        return

    added = sorted(n for n in fetched if n not in cards)
    for n, (key, _) in fetched.items():
        cards[n] = key

    lines = ['      <div class="cards">']
    for n in sorted(cards):
        lines.append(f'        <iframe class="note-embed" src="https://note.com/embed/notes/{cards[n]}" '
                     f'title="noteの記事 第{n}回" loading="lazy" height="210"></iframe>')
    lines.append('      </div>')
    new_html = head + start + '\n'.join(lines) + '\n' + end + tail

    newest = max(cards)
    if newest in fetched and fetched[newest][1]:
        w = fetched[newest][1]
        new_html = re.sub(r'<li>いちばん新しいのは、.*?です。</li>',
                          f'<li>いちばん新しいのは、{w.month}月{w.day}日に出した第{newest}回です。</li>', new_html)

    if new_html == html:
        print('新しい回は無い。ファイルはそのまま')
        return

    today = dt.datetime.now(JST)
    new_html = re.sub(r'最終更新 \d+年\d+月\d+日', f'最終更新 {today.year}年{today.month}月{today.day}日', new_html)
    io.open(path, 'w', encoding='utf-8', newline='').write(new_html.replace('\n', nl))
    print('足した回: ' + ('、'.join(f'第{n}回' for n in added) if added else 'なし（題名や日付の書き換えのみ）'))


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    main()
