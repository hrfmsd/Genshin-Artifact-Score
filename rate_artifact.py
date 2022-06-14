import translations as tr

import aiohttp
import asyncio
import os
import re
import sys
import numpy as np

from cv2 import cv2
from dotenv import load_dotenv
from fuzzywuzzy import fuzz, process
from unidecode import unidecode

load_dotenv()
OCR_API_KEY = os.getenv('OCR_SPACE_API_KEY')

reg = re.compile(r'\d+(?:[.,]\d+)?')
bad_reg = re.compile(r'\d+/1000$')
hp_reg = re.compile(r'\d[.,]\d{3}')
lvl_reg = re.compile(r'^\+\d\d?$')
bad_lvl_reg_1 = re.compile(r'^\+?\d\d?$')
bad_lvl_reg_2 = re.compile(r'^\d{4}\d*$')


async def ocr(url, num, lang=tr.ja()):
    if not OCR_API_KEY:
        print('Error: OCR_SPACE_API_KEY not found')
        return False, 'Error: OCR_SPACE_API_KEY not found'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            size = int(r.headers['Content-length'])
            if size > 5e6:
                img = np.asarray(bytearray(await r.read()), dtype="uint8")
                flag = cv2.IMREAD_GRAYSCALE
                if size > 8e6 or os.path.splitext(url)[1] == '.jpg':
                    flag = cv2.IMREAD_REDUCED_GRAYSCALE_2
                img = cv2.imdecode(img, flag)
                _, img = cv2.imencode('.png', img)
                data = aiohttp.FormData()
                data.add_field('apikey', OCR_API_KEY)
                if lang.supported:
                    data.add_field('OCREngine', '2')
                else:
                    data.add_field('language', lang.code)
                data.add_field('file', img.tobytes(), content_type='image/png', filename='image.png')
                ocr_url = f'https://apipro{num}.ocr.space/parse/image'
                async with session.post(ocr_url, data=data) as r:
                    json = await r.json()
            else:
                ocr_url = f'https://apipro{num}.ocr.space/parse/imageurl?apikey={OCR_API_KEY}&url={url}'
                if lang.supported:
                    ocr_url += '&OCREngine=2'
                else:
                    ocr_url += f'&language={lang.code}'
                async with session.get(ocr_url) as r:
                    json = await r.json()
            print(f'OCR Response: {json}')
            if json['OCRExitCode'] != 1:
                return False, f'{lang.err}: ' + '. '.join(json['ErrorMessage'])
            if 'ParsedResults' not in json:
                return False, lang.err_unknown_ocr
            return True, json['ParsedResults'][0]['ParsedText']


# OCR解析
def parse(text, lang=tr.ja()):
    stat = None
    results = []
    level = None
    prev = None
    del_prev = True

    elements = [lang.anemo, lang.elec, lang.pyro, lang.hydro, lang.cryo, lang.geo, lang.dend]
    choices = elements + [lang.hp, lang.heal, lang.df, lang.er, lang.em, lang.atk, lang.cd, lang.cr, lang.phys]
    choices = {unidecode(choice).lower(): choice for choice in choices}

    for line in text.splitlines():
        if not line:
            continue

        if del_prev:
            prev = None
        del_prev = True

        for k, v in lang.replace.items():
            line = line.replace(k, v)
        line = unidecode(line).lower()
        line = line.replace(':', '.').replace('-', '').replace('0/0', '%')
        if line.replace(' ', '') in lang.ignore or bad_reg.search(line.replace(' ', '')):
            continue
        if fuzz.partial_ratio(line, unidecode(lang.piece_set).lower()) > 80 and len(line) > 4:
            break

        value = lvl_reg.search(line.replace(' ', ''))
        if value:
            if level == None or (len(results) == 1 and not stat):
                print('1', line)
                level = int(value[0].replace('+', ''))
            continue

        value = hp_reg.search(line.replace(' ', ''))
        if value:
            print('2', line)
            value = int(value[0].replace(',', '').replace('.', ''))
            results += [[lang.hp, value]]
            stat = None
            continue

        extract = process.extractOne(line, list(choices))
        if extract[1] <= 80:
            extract = process.extractOne(line, list(choices), scorer=fuzz.partial_ratio)

        if ((extract[1] > 80) and len(line.replace(' ', '')) > 1) or stat:
            print('3', line)
            if (extract[1] > 80):
                stat = choices[extract[0]]
            value = reg.findall(line.replace(' ', '').replace(',', '.'))
            if not value:
                if not prev:
                    continue
                print('4', prev)
                value = prev
            value = max(value, key=len)
            if len(value) < 2:
                continue
            if line.find('%', line.find(value)) != -1 and '.' not in value:
                value = value[:-1] + '.' + value[-1]
            if '.' in value:
                value = float(value)
                stat += '%'
            else:
                value = int(value)
            results += [[stat, value]]
            stat = None
            if len(results) == 5:
                break
            continue

        value = bad_lvl_reg_1.search(line.replace(' ', '')) or bad_lvl_reg_2.search(
            line.replace(' ', '').replace('+', ''))
        if not value:
            line = line.replace(',', '')
            prev = reg.findall(line.replace(' ', ''))
            del_prev = False

    print(level, results)
    return level, results

# 値チェック
def validate(value, max_stat, is_percent):
    # 1.05は何？
    while value > max_stat * 1.05:
        value = str(value)
        removed = False
        for i in reversed(range(1, len(value))):
            if value[i] == value[i - 1]:
                value = value[:i - 1] + value[i:]
                removed = True
                break
        if not removed:
            if is_percent:
                pos = value.find('.')
                value = value[:pos - 1] + value[pos:]
            else:
                value = value[:-1]
        value = float(value) if is_percent else int(value)
    if int(value) == 1:
        value += 10
    return value


# スコア算出
def rate(level, results, options={}, lang=tr.ja()):
    sub_op_score = 0.0

    elements = [lang.anemo, lang.elec, lang.pyro, lang.hydro, lang.cryo, lang.geo, lang.dend]

    max_subs = {lang.atk: 19.0, lang.em: 23.0, f'{lang.er}%': 6.5, f'{lang.atk}%': 5.8,
                f'{lang.cr}%': 3.9, f'{lang.cd}%': 7.8, lang.df: 23.0, lang.hp: 299.0, f'{lang.df}%': 7.3,
                f'{lang.hp}%': 5.8}
    weights = {lang.hp: 0, lang.atk: 0, f'{lang.atk}%': 1, f'{lang.er}%': 0, lang.em: 0,
               f'{lang.phys}%': 0, f'{lang.cr}%': 2, f'{lang.cd}%': 1, f'{lang.elem}%': 0,
               f'{lang.hp}%': 0, f'{lang.df}%': 0, lang.df: 0, f'{lang.heal}%': 0}

    # Replaces weights with options
    weights = {**weights, **options}

    # サブOPスコアリング
    for result in results[1:]:
        stat, value = result
        print(f'stat: {stat} / value: {value}')

        key = stat if stat[:-1] not in elements else f'{lang.elem}%'

        value = validate(value, max_subs[key] * 6, '%' in key)
        sub_op_score += value * weights[key]
        print(key, (value * weights[key]))

        result[1] = value

    return sub_op_score


if __name__ == '__main__':
    if sys.version_info[0] == 3 and sys.version_info[1] >= 8 and sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # fig.1
    url = 'https://cdn.discordapp.com/attachments/875789875918561331/951863634441691146/unknown.png'

    options = {}
    lang = tr.ja()
    success, text = asyncio.run(ocr(url, 2, lang))
    # print(text)
    if success:
        level, results = parse(text, lang)
        rate(level, results, options, lang)
