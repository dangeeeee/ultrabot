.PHONY: up down restart logs build shell db-shell redis-shell backup status migrate help

help:
	@echo ""
	@echo "  🖥️  VPS Shop Bot — команды управления"
	@echo ""
	@echo "  Запуск:"
	@echo "    make up           Запустить все сервисы"
	@echo "    make down         Остановить все сервисы"
	@echo "    make restart      Перезапустить только бота"
	@echo "    make build        Пересобрать Docker образ"
	@echo ""
	@echo "  Логи и мониторинг:"
	@echo "    make logs         Логи бота в реальном времени"
	@echo "    make status       Статус и ресурсы контейнеров"
	@echo ""
	@echo "  База данных:"
	@echo "    make migrate      Запустить Alembic миграции"
	@echo "    make db-shell     PostgreSQL консоль"
	@echo "    make backup       Создать бекап БД"
	@echo ""
	@echo "  Отладка:"
	@echo "    make shell        Bash внутри контейнера бота"
	@echo "    make redis-shell  Redis CLI"
	@echo ""

up:
	@mkdir -p logs data/backups
	@chmod 755 logs data
	docker compose up -d
	@echo ""
	@echo "✅ Все сервисы запущены!"
	@echo "   Бот:  http://localhost:8080/health"
	@echo "   n8n:  https://$(shell grep N8N_DOMAIN .env 2>/dev/null | cut -d= -f2 || echo 'n8n.example.com')"
	@echo ""

down:
	docker compose down

restart:
	docker compose restart bot
	@echo "⏳ Ждём запуска..."
	@sleep 3
	docker compose logs --tail=20 bot

logs:
	docker compose logs -f bot

build:
	docker compose build bot
	docker compose up -d bot

shell:
	docker compose exec bot bash

db-shell:
	docker compose exec postgres psql -U $$(grep POSTGRES_USER .env | cut -d= -f2 || echo vpsbot) -d $$(grep POSTGRES_DB .env | cut -d= -f2 || echo vpsbot)

redis-shell:
	docker compose exec redis redis-cli -a $$(grep REDIS_PASSWORD .env | cut -d= -f2 || echo redispass)

migrate:
	docker compose exec bot python -m alembic upgrade head
	@echo "✅ Миграции применены"

backup:
	@mkdir -p data/backups
	docker compose exec -T postgres pg_dump \
		-U $$(grep POSTGRES_USER .env | cut -d= -f2 || echo vpsbot) \
		$$(grep POSTGRES_DB .env | cut -d= -f2 || echo vpsbot) \
		> data/backups/backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "✅ Бекап сохранён в data/backups/"

status:
	@echo "=== Контейнеры ==="
	docker compose ps
	@echo ""
	@echo "=== Ресурсы ==="
	docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
