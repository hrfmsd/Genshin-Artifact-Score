import translations as tr

import aiohttp
import asyncio
import os
import re
import sys
import numpy as np
import math

from cv2 import cv2
from dotenv import load_dotenv
from fuzzywuzzy import fuzz, process
from unidecode import unidecode

load_dotenv()
OCR_API_KEY = os.getenv('OCR_SPACE_API_KEY')

# regex
reg = re.compile(r'\d+(?:[.,]\d+)?')
num_reg = re.compile(r'^(\+)?\d+([.,]\d{1,3})?%?$')
bad_reg = re.compile(r'\d+/1000$')
hp_reg = re.compile(r'\d[.,]\d{3}')
atk_reg = re.compile(r'^\+?\d?[.,]?\d{3}')
bad_lvl_reg_1 = re.compile(r'^\+?\d\d?$')
bad_lvl_reg_2 = re.compile(r'^\d{4}\d*$')


# OCR APIに解析してもらった結果を返す
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


# OCR APIの解析結果を解析
def parse(text, options, lang=tr.ja()):
    results = {
        lang.atk: 0,
        lang.atk_base: 0,
        lang.atk_add: 0,
        lang.atk_add_rate: 0,
        lang.cr: 0,
        lang.cd: 0,
        lang.er: 0,
        lang.em: 0,
        lang.em_effect_1: 0,
        lang.em_effect_2: 0,
        lang.em_effect_3: 0,
    }
    
    buffs = {}

    positions = {
        lang.atk_base: 1,
        lang.atk_add: 13,
        lang.cr: 4,
        lang.cd: 5,
        lang.er: 8,
        lang.em: 3,
    }

    values = []

    # elements = []
    # choices = elements + [lang.atk, lang.cr, lang.cd, lang.er, lang.em]
    # choices = {unidecode(choice).lower(): choice for choice in choices}

    lines = text.splitlines()
    line_count = len(lines)
    print('行数：', line_count)

    if line_count == 35:
        positions = {
            lang.atk_base: 1,
            lang.atk_add: 13,
            lang.cr: 5,
            lang.cd: 6,
            lang.er: 9,
            lang.em: 3,
        }
    elif line_count == 36:
        positions = {
            lang.atk_base: 1,
            lang.atk_add: 13,
            lang.cr: 5,
            lang.cd: 6,
            lang.er: 9,
            lang.em: 3,
        }
    elif line_count == 34:
        positions = {
            lang.atk_base: 1,
            lang.atk_add: 12,
            lang.cr: 4,
            lang.cd: 5,
            lang.er: 8,
            lang.em: 99,
        }

    print('============')
    for idx, line in enumerate(lines):
        if not line:
            continue

        for k, v in lang.replace.items():
            line = line.replace(k, v)

        line = unidecode(line).lower()
        line = line.replace(':', '.').replace('-', '').replace('0/0', '%')
        line = line.replace('\'', '').replace('*', '')
        line_replaced = line.replace(' ', '')
        if line_replaced in lang.ignore or bad_reg.search(line_replaced):
            continue

        # 元素熟知の説明文を無視
        has_ignore = False
        for each_reg in lang.ignore_regs:
            each_reg_unidecode = re.compile(re.escape(unidecode(each_reg).lower().replace(' ', '')) + r'(\+\d[.,]\d%)?')
            # print('diff:', each_reg_unidecode, line.replace(' ', ''))
            if each_reg_unidecode.search(line_replaced):
                # print('ignore:', line_replaced)
                has_ignore = True
                break

        if has_ignore:
            continue

        # fuzzywuzzyによる近似探索
        # extract = process.extractOne(line, list(choices))
        # # print('ext1:', extract, line)
        # if extract[1] <= 80:
        #     extract = process.extractOne(line, list(choices), scorer=fuzz.partial_ratio)
        #     # print('ext2:', extract)
        #
        # if extract[1] > 90:
        #     # stat = choices[extract[0]]
        #     # results[stat] = [[stat, '', '']]
        #     continue

        # 14-15件（熟知の数値[3]がOCRの問題で取得できない時がある）
        if num_reg.fullmatch(line_replaced):
            # if line_replaced != '0':
            # 先頭の2件はOCRによる謎の読み取り値「0」
            if idx >= 20:
                print(idx, line_replaced)
                values += [line_replaced]

    for k in results.keys():
        if k == lang.atk_base:
            results[k] = int(values[1].replace(',', ''))
            continue
        if k == lang.atk_add:
            results[k] = int(values[positions[k]].replace(',', '').replace('+', ''))
        if k == lang.cr:
            results[k] = float(values[positions[k]].replace('%', ''))
            continue
        if k == lang.cd:
            results[k] = float(values[positions[k]].replace('%', ''))
            continue
        if k == lang.er:
            results[k] = float(values[positions[k]].replace('%', ''))
            continue
        if k == lang.em:
            if values[positions[k]:positions[k] + 1]:
                results[k] = int(values[positions[k]].replace(',', ''))
            else:
                results[k] = 0
            continue

    # options
    if options:
        for k, v in options.items():
            if k == lang.atk:
                results[lang.atk_add] += int(v)
                buffs[lang.atk_add] = int(v)
                continue
            if k == lang.atk_add_rate:
                results[lang.atk_add_rate] += float(v)
                buffs[lang.atk_add_rate] = float(v)
                continue
            if k == lang.cr:
                results[lang.cr] += float(v)
                buffs[lang.cr] = float(v)
                continue
            if k == lang.cd:
                results[lang.cd] += float(v)
                buffs[lang.cd] = float(v)
                continue

    results[lang.atk] = results[lang.atk_base] + results[lang.atk_add]
    results[lang.atk_add_rate] = round(results[lang.atk_add_rate] + float(results[lang.atk_add] / results[lang.atk_base]) * 100, 1)

    if results[lang.em] > 0:
        results[lang.em_effect_1] = round((1.0 * 25 * results[lang.em] / (9 * (results[lang.em] + 1400))), 3)
        results[lang.em_effect_2] = round(16 * results[lang.em] / (results[lang.em] + 2000), 3)
        results[lang.em_effect_3] = round(1.6 * 25 * results[lang.em] / (9 * (results[lang.em] + 1400)), 3)

    print('============\n', results)
    print('============\n', buffs)
    return results, buffs


# スコア付け
def rate(results, lang=tr.ja()):
    score = 100
    ideal_results = {
        'score_message': ''
    }
    atk_base = 0
    atk_add = 0
    cr = 0.5
    cd = 100

    for k, v in results.items():
        if k == lang.atk_base:
            atk_base = v
            continue
        if k == lang.atk_add:
            atk_add = v
            continue
        if k == lang.cr:
            cr = v / 100
            continue
        if k == lang.cd:
            cd = v / 100
            continue

    # calc（攻撃力％：会心率：会心ダメージ=1.5：1：2）
    n_atk = atk_base * 1
    atk_add_rate = 0 if atk_base == 0 else (atk_add / atk_base)
    c_atk = n_atk

    # 理想値計算：ダメージ上昇効率で場合分けする
    # 会心率：会心ダメージの理想配分は１：２
    # 聖遺物の攻撃力：会心率：会心ダメージの伸び率は1.5：１：２
    # 聖遺物のサブOPにおける実際の伸び率は運ゲーなので高スコアを優先する
    # 会心率 <= 0.25においては攻撃力を伸ばす方がダメージ上昇効率が高い
    # 0.25 <= 会心率 <= 0.5におけるダメージ上昇効率は2.5〜4.2
    # 0.5 <= 会心率 <= 1におけるダメージ上昇効率は4.2〜4.5
    # 特に会心率が0.7付近の時にダメージ上昇効率が4.5付近と最も高い
    # 加算攻撃力比率:ar= 加算攻撃力（緑）/ 基礎攻撃力（白）
    # 1.2 <= ar <= 1.3におけるダメージ上昇効率は会心系のそれよりも高い(4.35以上)
    # 加算攻撃力（緑）は固定値系やバフもすべて含めた割合とする

    ideal_atk_add_rate = 1.2
    ideal_cr = 0.7
    ideal_cd = 1.4

    # 攻撃・会心における装備スコア計算
    stat_rate_limit_low = 2.45
    stat_rate_base = 2.828
    stat_rate = (1 + atk_add / atk_base) / 1.5 + cr + cd / 2

    if stat_rate < stat_rate_limit_low:
        if atk_add_rate < 1.2:
            art_diff_add_rate = (ideal_atk_add_rate - atk_add_rate) / 1.5 / 2
            ideal_cr = 0.05 if cr - art_diff_add_rate < 0.05 else cr - art_diff_add_rate
            ideal_cd = 0.5 if cd - art_diff_add_rate * 2 < 0.5 else cd - art_diff_add_rate * 2
            ideal_cr, ideal_cd = adjust_cr_over_limit(ideal_cr, ideal_cd)
        elif 1.2 <= atk_add_rate <= 1.3:
            ideal_atk_add_rate = atk_add_rate
        else:
            art_diff_add_rate = (ideal_atk_add_rate - atk_add_rate) / 1.5 / 2
            ideal_cr = 0.05 if cr - art_diff_add_rate < 0.05 else cr - art_diff_add_rate
            ideal_cd = 0.5 if cd - art_diff_add_rate * 2 < 0.5 else cd - art_diff_add_rate * 2
            ideal_cr, ideal_cd = adjust_cr_over_limit(ideal_cr, ideal_cd)
    else:
        ideal_atk_add_rate = (2 * stat_rate - math.sqrt((stat_rate * stat_rate - 12 / 2))) / 3 * 1.5 - 1
        ideal_cr = (stat_rate + math.sqrt(stat_rate * stat_rate - 12 / 2)) / 6
        ideal_cr = 0.05 if ideal_cr < 0.05 else ideal_cr
        ideal_cd = ideal_cr * 2
        ideal_cr, ideal_cd = adjust_cr_over_limit(ideal_cr, ideal_cd)

    # 装備スコアメッセージ
    # if stat_rate < stat_rate_limit_low:
    #     ideal_results['score_message'] += 'アタッカーではないか、育成が足りないようです\n'
    # elif stat_rate_limit_low <= stat_rate < stat_rate_base:
    #     ideal_results['score_message'] += 'まだ聖遺物が十分ではないようです\n'
    # else:
    #     ideal_results['score_message'] += 'さらなる高みを目指しましょう\n'

    # 配分メッセージ
    if atk_add_rate < 1.2:
        ideal_results['score_message'] += '会心系を下げてでも攻撃力を上げましょう\n'
    elif 1.2 <= atk_add_rate <= 1.3:
        ideal_results['score_message'] += '攻撃力は適正なのでそのまま会心系を上げましょう\n'
    else:
        ideal_results['score_message'] += '攻撃力を下げてでも会心系を上げましょう\n'

    dmg = calc_dmg(atk_base, atk_add_rate, cr, cd)
    ideal_dmg = calc_dmg(atk_base, ideal_atk_add_rate, ideal_cr, ideal_cd)
    dmg_diff_rate = (dmg / ideal_dmg - 1)

    print('============')
    print(f'stat_rate:{stat_rate}')
    print(f'atk_add_rate:{atk_add_rate}')
    print(f'ideal_atk_add_rate:{ideal_atk_add_rate}')
    print(f'cr:{cr}')
    print(f'ideal_cr:{ideal_cr}')
    print(f'cd:{cd}')
    print(f'ideal_cd:{ideal_cd}')
    print('============')
    print(f'dmg:{dmg}')
    print(f'ideal_dmg:{ideal_dmg}')
    print('============')

    # 理想値とのダメージ差
    print(f'理想値とのダメージ差：{dmg_diff_rate:.2%}')
    # 同じ装備スコアの理想値
    print(f'理想+攻撃力(緑)：{round(atk_base * ideal_atk_add_rate):,}')
    # 同じ装備スコアの理想値
    print(f'理想会心率：{ideal_cr:.1%}')
    # 同じ装備スコアの理想値
    print(f'理想会心ダメージ：{ideal_cd:.1%}')
    print('============')

    ideal_results['dmg_diff_rate'] = dmg_diff_rate
    ideal_results['ideal_atk_add'] = round(atk_base * ideal_atk_add_rate)
    ideal_results['ideal_atk_add_rate'] = round(atk_base * ideal_atk_add_rate / atk_base, 3)
    ideal_results['ideal_cr'] = ideal_cr
    ideal_results['ideal_cd'] = ideal_cd
    ideal_results['exp_dmg_v'] = round(dmg)
    ideal_results['ideal_exp_dmg_v'] = round(ideal_dmg)
    # ideal_results['exp_dmg_v'] = round(exp_dmg_v)
    # ideal_results['ideal_exp_dmg_v'] = round(ideal_exp_dmg_v)

    # score
    dmg_diff_rate_score = round(dmg_diff_rate * 100, 1)

    # ダメージ差による減点
    if 0 < dmg_diff_rate_score <= 5:
        score += dmg_diff_rate_score * 2.5
    elif 5 < dmg_diff_rate_score <= 10:
        score += dmg_diff_rate_score * 3
    else:
        score += dmg_diff_rate_score * 5

    # 装備スコアによる減点
    score = score - 4.5 + round(stat_rate, 1)

    print(f'スコア：{score}点', ideal_results)
    print('============\n')
    return score, ideal_results


def calc_dmg(atk_base, atk_add_rate, cr, cd):
    cr = cr if cr < 1 else 1
    return (atk_base * (1 + atk_add_rate)) * (1 + cr * cd)


def adjust_cr_over_limit(cr, cd):
    if cr > 1:
        cr_diff = cr - 1
        cr = 1
        cd += cr_diff * 2

    return cr, cd


if __name__ == '__main__':
    if sys.version_info[0] == 3 and sys.version_info[1] >= 8 and sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # 36 / kujo
    url = 'https://media.discordapp.net/attachments/884021052575985745/886237270007492628/unknown.png'
    # 35 / scro
    # url = 'https://media.discordapp.net/attachments/884021052575985745/886236071212494898/unknown.png'
    # 36 / nana
    # url = 'https://media.discordapp.net/attachments/884021052575985745/886202524024070144/unknown.png'
    # 35 / sho
    # url = 'https://media.discordapp.net/attachments/884021052575985745/886188859795329034/unknown.png'
    # 34 / syanrin
    # url = 'https://media.discordapp.net/attachments/884021052575985745/886187208636260352/unknown.png'
    # 35 / hokuto
    # url = 'https://media.discordapp.net/attachments/884021052575985745/886183282172116992/unknown.png'
    # 35 / kazuha
    # url = 'https://media.discordapp.net/attachments/884021052575985745/886141996647981078/unknown.png'
    # 34 / yoimiya
    # url = 'https://media.discordapp.net/attachments/884021052575985745/886130399737184276/unknown.png'
    # 34 / taru
    # url = 'https://media.discordapp.net/attachments/884021052575985745/885676688367824956/2021-09-10_090247.png'
    # 35 / kannu
    # url = 'https://media.discordapp.net/attachments/884021052575985745/884384521993203752/unknown.png'
    # 35 / raiden
    # url = 'https://media.discordapp.net/attachments/884021052575985745/884299376917381171/unknown.png'
    # url = 'https://media.discordapp.net/attachments/884021052575985745/884041657790652436/unknown.png'
    # url = 'https://media.discordapp.net/attachments/884021052575985745/884032862591004682/unknown.png'
    # 34 / ayaka
    # url = 'https://media.discordapp.net/attachments/875974646195970118/882272611646726204/unknown.png'
    # 34 /
    # url = 'https://media.discordapp.net/attachments/875974646195970118/882272755163234324/unknown.png'

    options = {}
    lang = tr.ja()
    success, text = asyncio.run(ocr(url, 2, lang))
    # print(text)
    if success:
        results, buffs = parse(text, options, lang)
        rate(results, lang)
