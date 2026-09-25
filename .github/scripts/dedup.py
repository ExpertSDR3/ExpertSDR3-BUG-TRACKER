import os
import sys
import requests

token = os.environ.get("GITHUB_TOKEN")
repo = os.environ.get("REPO")
target_num = os.environ.get("TARGET_ISSUE_NUM")

if not token or not repo or not target_num:
    print("Ошибка: Не заданы обязательные переменные окружения.")
    sys.exit(1)

gh_headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "GitHub-Action-Issue-Dedup"
}

# 1. Получаем целевую задачу
print(f"Запрос Issue #{target_num}...")
issue_res = requests.get(f"https://api.github.com/repos/{repo}/issues/{target_num}", headers=gh_headers)
if issue_res.status_code != 200:
    print(f"Ошибка получения Issue #{target_num}: {issue_res.status_code}\n{issue_res.text}")
    sys.exit(1)

target_issue = issue_res.json()
print(f"Анализируем: #{target_issue['number']} - {target_issue.get('title')}")

# 2. Получаем список задач для сравнения
list_res = requests.get(f"https://api.github.com/repos/{repo}/issues?state=all&per_page=50", headers=gh_headers)
if list_res.status_code != 200:
    print(f"Ошибка получения списка задач: {list_res.status_code}\n{list_res.text}")
    sys.exit(1)

issues_list = list_res.json()
candidates = []
for item in issues_list:
    if str(item.get("number")) != str(target_num) and "pull_request" not in item:
        preview = (item.get("body") or "")[:250].replace("\n", " ")
        candidates.append(f"#{item['number']}: {item['title']} (Контекст: {preview})")

if not candidates:
    print("Нет других задач для сравнения.")
    sys.exit(0)

prompt = f"""Ты — дежурный технический модератор репозитория ExpertSDR3.
Проверь, дублирует ли новая задача одну из существующих проблем.

ЦЕЛЕВАЯ ЗАДАЧА:
#{target_issue['number']}: {target_issue.get('title')}
Описание:
{target_issue.get('body', '')}

ДРУГИЕ ЗАДАЧИ:
{"\n".join(candidates)}

ИНСТРУКЦИЯ:
- Если ЦЕЛЕВАЯ ЗАДАЧА описывает ту же аппаратную/программную неисправность, ответь строго в формате:
DUPLICATE: #НОМЕР (кратко опиши причину)
- Если совпадений нет, ответь строго одним словом:
UNIQUE
"""

# 3. Запрос к GitHub Models
ai_headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "User-Agent": "GitHub-Action-Issue-Dedup"
}
ai_payload = {
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0.1
}

print("Отправка запроса в GitHub Models API...")
ai_res = requests.post(
    "https://models.github.ai/inference/chat/completions",
    headers=ai_headers,
    json=ai_payload
)

print(f"Статус ответа модели: {ai_res.status_code}")
if ai_res.status_code != 200:
    print(f"Ошибка вызова модели ({ai_res.status_code}):\n{ai_res.text}")
    sys.exit(1)

try:
    data = ai_res.json()
    answer = data["choices"][0]["message"]["content"].strip()
    print(f"Результат анализа:\n{answer}")
except Exception as e:
    print(f"Ошибка разбора ответа ({e}). Сырой ответ сервера:\n>>>{ai_res.text}<<<")
    sys.exit(1)

# 4. Если дубликат — комментируем и ставим метку
if "DUPLICATE:" in answer:
    comment_body = f"🤖 **AI Issue Deduplicator**\n\n{answer}\n\nПожалуйста, ознакомьтесь с обсуждением в указанном тикете."
    requests.post(
        f"https://api.github.com/repos/{repo}/issues/{target_num}/comments",
        headers=gh_headers,
        json={"body": comment_body}
    )
    requests.post(
        f"https://api.github.com/repos/{repo}/issues/{target_num}/labels",
        headers=gh_headers,
        json={"labels": ["duplicate"]}
    )
    print("Метка duplicate и комментарий добавлены.")
else:
    print("Дубликатов не найдено.")
