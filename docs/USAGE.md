# Руководство по использованию Embedding Service

## 1. Отправка документа на обработку

Вы можете отправлять `.md` или `.txt` файлы. Система автоматически очистит их от разметки.

### Через curl:
```bash
curl -X POST http://localhost:8001/api/async/embedding/submit \
  -F "file=@document.md"
```

### Через Python:
Смотри готовый пример в [docs/examples/submit_job.py](examples/submit_job.py).

---

## 2. Мониторинг статуса

Во время обработки можно опрашивать статус. Поле `progress` покажет этап выполнения (от 0 до 100).

```bash
curl http://localhost:8001/api/async/embedding/status/{job_id}
```

---

## 3. Получение результата (BLOB)

Когда статус станет `done`, вы можете скачать бинарный файл.

```bash
curl -O -J http://localhost:8001/api/async/embedding/result/{job_id}
```

### Структура BLOB:
Результат сериализован с помощью библиотеки `pickle` и представляет собой список векторов (numpy arrays).

```python
import pickle

with open("embedding_job.blob", "rb") as f:
    embeddings = pickle.load(f)

print(f"Получено векторов: {len(embeddings)}")
```

---

## 4. Панель мониторинга (Dashboard)

Просто откройте [http://localhost:8001/](http://localhost:8001/) в браузере. 
Панель поддерживает:
- Авто-обновление каждые 5 секунд.
- Фильтрацию по статусам (`queued`, `processing`, `done`, `failed`).
- Пагинацию (если задач много).

---

## 5. Очистка текста (Text Cleaning)
Сервис применяет следующие правила перед энкодингом:
1. Удаление Markdown заголовков (`#`, `##`).
2. Извлечение текста из ссылок (`[Text](URL)` -> `Text`).
3. Удаление маркеров выделения (`**`, `__`, `*`, `_`).
4. Удаление невидимых управляющих символов.
5. Схлопывание лишних пробелов.
