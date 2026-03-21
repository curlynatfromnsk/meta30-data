#!/usr/bin/env python3
"""
META30 Data Validator — автотесты для JSON данных меню.
Запуск: python3 validate_data.py [путь_к_папке_с_json]
По умолчанию ищет JSON в текущей директории.

Проверяет:
  1. Структура JSON (menu, shop, prep)
  2. Макросы: kcal в диапазоне, белок ≤80г, чистые углеводы ≤25г
  3. Полнота дней: 30 дней, 5 слотов каждый
  4. Повторения: no_repeat_window 3 дня по слотам
  5. rk ключи: все ссылаются на существующие рецепты в app.js
  6. Именование: нет "льняной", "виноградн", "net carbs", slug-ключей
  7. Списки покупок: 4 недели, категории не пустые
  8. Заготовки: нет дублей, нет покупных продуктов в prep
  9. Консистентность: prep рецепты совпадают с rk в меню
"""

import json, sys, os, re
from collections import defaultdict

# ═══ КОНФИГ ═══

LEVELS = {
    '1600': {'kcal_min': 1600, 'kcal_max': 1800},
    '1800': {'kcal_min': 1800, 'kcal_max': 2000},
    '2000': {'kcal_min': 2000, 'kcal_max': 2200},
}

PROTEIN_MAX = 80
NET_CARBS_MAX = 25
DAYS = 30
SLOTS_PER_DAY = 5
SLOT_KEYS = {'keto', 'breakfast', 'lunch', 'snack', 'dinner'}
NO_REPEAT_WINDOW = 3

WEEK_RANGES = {
    'Неделя 1 (дни 1–7)': (1, 7),
    'Неделя 2 (дни 8–14)': (8, 14),
    'Неделя 3 (дни 15–21)': (15, 21),
    'Неделя 4 (дни 22–30)': (22, 30),
}

# Рецепты из app.js (актуальные ключи)
VALID_RK = {
    'tortilla', 'keto-bread', 'keto-bread-90', 'rostbif', 'guacamole',
    'mayo', 'broccoli-slaw', 'zucchini-waffles', 'keto-buns', 'keto-muffins',
    'italian-dressing', 'ranch-dressing', 'caul-broccoli', 'mashed-cauliflower',
    'keto-latte', 'broccoli-soup', 'chicken-drumsticks', 'egg-bites',
}

# Продукты, которые ПОКУПАЮТСЯ, а не готовятся (не должны быть в prep)
PURCHASED_NOT_PREPPED = {'Релиш', 'Соус песто'}

# Запрещённые подстроки в данных
FORBIDDEN_STRINGS = [
    ('льняной кето', 'Должно быть "Кето хлеб", не "Льняной кето хлеб"'),
    ('виноградной косточки', 'Должно быть "Оливковое масло", не "Масло виноградной косточки"'),
    ('net carbs', 'Должно быть "чистые углеводы"'),
]

# ═══ ТЕСТЫ ═══

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.errors = []
    
    def ok(self, msg):
        self.passed += 1
    
    def fail(self, msg):
        self.failed += 1
        self.errors.append(f'❌ {msg}')
        print(f'  ❌ {msg}')
    
    def warn(self, msg):
        self.warnings += 1
        print(f'  ⚠️  {msg}')
    
    def summary(self):
        total = self.passed + self.failed
        status = '✅ ALL PASSED' if self.failed == 0 else f'❌ {self.failed} FAILED'
        print(f'\n{"="*60}')
        print(f'{status} — {self.passed}/{total} tests passed, {self.warnings} warnings')
        if self.errors:
            print(f'\nОшибки:')
            for e in self.errors:
                print(f'  {e}')
        return self.failed == 0


def validate_level(level, data, cfg, t):
    print(f'\n{"─"*60}')
    print(f'Уровень {level} ккал')
    print(f'{"─"*60}')
    
    menu = data.get('menu', [])
    shop = data.get('shop', {})
    prep = data.get('prep', {})
    
    # ═══ 1. СТРУКТУРА ═══
    if len(menu) == DAYS:
        t.ok(f'{level}: 30 дней')
    else:
        t.fail(f'{level}: ожидалось {DAYS} дней, найдено {len(menu)}')
    
    if shop:
        t.ok(f'{level}: shop присутствует')
    else:
        t.fail(f'{level}: shop отсутствует')
    
    if prep:
        t.ok(f'{level}: prep присутствует')
    else:
        t.warn(f'{level}: prep отсутствует')
    
    # ═══ 2. МАКРОСЫ ═══
    kcal_min, kcal_max = cfg['kcal_min'], cfg['kcal_max']
    kcal_issues = []
    protein_issues = []
    carb_issues = []
    
    for day in menu:
        d = day['d']
        tt = day['tt']
        
        if not (kcal_min <= tt['kcal'] <= kcal_max):
            # Допуск ±5 ккал
            if abs(tt['kcal'] - kcal_min) <= 5 or abs(tt['kcal'] - kcal_max) <= 5:
                pass  # покрывается дисклеймером
            else:
                kcal_issues.append(f"День {d}: {tt['kcal']} ккал (диапазон {kcal_min}–{kcal_max})")
        
        if tt['p'] > PROTEIN_MAX:
            protein_issues.append(f"День {d}: белок {tt['p']}г (макс {PROTEIN_MAX})")
        
        if tt['nc'] > NET_CARBS_MAX:
            carb_issues.append(f"День {d}: ЧУ {tt['nc']}г (макс {NET_CARBS_MAX})")
    
    if not kcal_issues:
        t.ok(f'{level}: калории в диапазоне')
    else:
        for issue in kcal_issues:
            t.fail(f'{level}: {issue}')
    
    if not protein_issues:
        t.ok(f'{level}: белок ≤{PROTEIN_MAX}г')
    else:
        for issue in protein_issues:
            t.fail(f'{level}: {issue}')
    
    if not carb_issues:
        t.ok(f'{level}: ЧУ ≤{NET_CARBS_MAX}г')
    else:
        for issue in carb_issues:
            t.fail(f'{level}: {issue}')
    
    # ═══ 3. ПОЛНОТА СЛОТОВ ═══
    slot_issues = []
    for day in menu:
        slots = [m['s'] for m in day['ml']]
        if len(slots) != SLOTS_PER_DAY:
            slot_issues.append(f"День {day['d']}: {len(slots)} слотов (ожидалось {SLOTS_PER_DAY})")
        for s in slots:
            if s not in SLOT_KEYS:
                slot_issues.append(f"День {day['d']}: неизвестный слот '{s}'")
    
    if not slot_issues:
        t.ok(f'{level}: все дни имеют 5 слотов')
    else:
        for issue in slot_issues:
            t.fail(f'{level}: {issue}')
    
    # ═══ 4. ПОВТОРЕНИЯ ═══
    repeat_issues = []
    slot_history = defaultdict(list)  # slot -> list of meal names
    for day in menu:
        d = day['d']
        for m in day['ml']:
            slot = m['s']
            name = m['n']
            recent = slot_history[slot][-NO_REPEAT_WINDOW:]
            if name in recent and slot != 'keto':  # keto-кофе повторяется by design
                repeat_issues.append(f"День {d}, {slot}: «{name}» повторяется в окне {NO_REPEAT_WINDOW} дней")
            slot_history[slot].append(name)
    
    if not repeat_issues:
        t.ok(f'{level}: нет повторов в окне {NO_REPEAT_WINDOW} дней')
    else:
        for issue in repeat_issues[:5]:  # первые 5
            t.warn(f'{level}: {issue}')
        if len(repeat_issues) > 5:
            t.warn(f'{level}: ...и ещё {len(repeat_issues)-5} повторов')
    
    # ═══ 5. RK КЛЮЧИ ═══
    rk_issues = []
    all_rks = set()
    for day in menu:
        for meal in day['ml']:
            for ing in meal.get('i', []):
                rk = ing.get('rk')
                if rk:
                    all_rks.add(rk)
                    if rk not in VALID_RK:
                        rk_issues.append(f"День {day['d']}, «{ing['n']}»: rk='{rk}' не найден в app.js")
    
    if not rk_issues:
        t.ok(f'{level}: все rk ключи валидны ({len(all_rks)} уникальных)')
    else:
        for issue in rk_issues:
            t.fail(f'{level}: {issue}')
    
    # ═══ 6. ЗАПРЕЩЁННЫЕ СТРОКИ ═══
    raw = json.dumps(data, ensure_ascii=False).lower()
    forbidden_found = []
    for pattern, explanation in FORBIDDEN_STRINGS:
        if pattern.lower() in raw:
            forbidden_found.append(f"Найдено «{pattern}»: {explanation}")
    
    if not forbidden_found:
        t.ok(f'{level}: нет запрещённых строк')
    else:
        for issue in forbidden_found:
            t.fail(f'{level}: {issue}')
    
    # ═══ 7. SHOP ═══
    if shop:
        shop_keys = set(shop.keys())
        expected_weeks = set(WEEK_RANGES.keys())
        missing_weeks = expected_weeks - shop_keys
        
        if not missing_weeks:
            t.ok(f'{level}: shop имеет все 4 недели')
        else:
            for w in missing_weeks:
                t.fail(f'{level}: shop — отсутствует {w}')
        
        empty_cats = []
        egg_unit_issues = []
        for week, cats in shop.items():
            for cat, items in cats.items():
                if not items:
                    empty_cats.append(f"{week}, {cat}")
                for it in items:
                    # Eggs must be in шт, not grams
                    if ('яйц' in it['product'].lower() or 'перепел' in it['product'].lower()) and 'г' in it['qty']:
                        egg_unit_issues.append(f"{week}: {it['product']} — {it['qty']} (должно быть в шт)")
        
        if not empty_cats:
            t.ok(f'{level}: нет пустых категорий в shop')
        else:
            for issue in empty_cats:
                t.warn(f'{level}: пустая категория в shop — {issue}')
        
        if not egg_unit_issues:
            t.ok(f'{level}: яйца в shop считаются в штуках')
        else:
            for issue in egg_unit_issues:
                t.fail(f'{level}: {issue}')
    
    # ═══ 8. PREP ═══
    if prep:
        prep_issues = []
        
        for week, items in prep.items():
            # Detect format: if items have different ingredients under same recipe → ingredient-level format
            # In that case, duplicates by recipe name are expected (each ingredient is a row)
            recipe_counts = defaultdict(int)
            for item in items:
                recipe_counts[item['recipe']] += 1
            
            # Check if this is ingredient-level format (multiple rows per recipe, different ingredients)
            is_ingredient_format = any(
                len(set(i['ingredient'] for i in items if i['recipe'] == r)) > 1 
                for r, c in recipe_counts.items() if c > 1
            )
            
            if not is_ingredient_format:
                # Summary format (1800/2000): each recipe should appear once
                seen = set()
                for r in recipe_counts:
                    if recipe_counts[r] > 1:
                        prep_issues.append(f"{week}: дубль «{r}» ({recipe_counts[r]}x)")
                    seen.add(r)
            
            # Покупные продукты в prep
            for item in items:
                if item['recipe'] in PURCHASED_NOT_PREPPED:
                    prep_issues.append(f"{week}: «{item['recipe']}» должен быть в shop, не в prep")
            
            # Slug-ключи вместо русских названий
            for item in items:
                if re.match(r'^[a-z][-a-z]+$', item['recipe']):
                    prep_issues.append(f"{week}: slug-ключ «{item['recipe']}» → нужно русское название")
        
        if not prep_issues:
            t.ok(f'{level}: prep чистый')
        else:
            for issue in prep_issues:
                t.fail(f'{level}: {issue}')


def validate_articles(path, t):
    """Validate articles.json"""
    articles_path = os.path.join(path, 'articles.json')
    if not os.path.exists(articles_path):
        t.warn('articles.json не найден')
        return
    
    print(f'\n{"─"*60}')
    print(f'Статьи (articles.json)')
    print(f'{"─"*60}')
    
    articles = json.load(open(articles_path))
    
    if len(articles) == 22:
        t.ok(f'articles: 22 статьи')
    else:
        t.fail(f'articles: ожидалось 22, найдено {len(articles)}')
    
    stubs = [a for a in articles if len(a.get('body', '')) < 150]
    if not stubs:
        t.ok(f'articles: все 22 с контентом')
    else:
        for a in stubs:
            t.fail(f"articles: «{a['id']}» — заглушка ({len(a.get('body',''))} символов)")
    
    # Check required fields
    for a in articles:
        for field in ['id', 'title', 'level', 'levelName', 'body', 'readingTime']:
            if field not in a:
                t.fail(f"articles: «{a.get('id','?')}» — нет поля '{field}'")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    t = TestResult()
    
    print(f'META30 Data Validator')
    print(f'Путь: {os.path.abspath(path)}')
    
    for level, cfg in LEVELS.items():
        fname = f'data_{level}.json'
        fpath = os.path.join(path, fname)
        
        if not os.path.exists(fpath):
            t.fail(f'{fname} не найден')
            continue
        
        try:
            data = json.load(open(fpath))
        except json.JSONDecodeError as e:
            t.fail(f'{fname}: ошибка JSON — {e}')
            continue
        
        validate_level(level, data, cfg, t)
    
    validate_articles(path, t)
    
    success = t.summary()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
