.PHONY: backend frontend test

backend:
	uvicorn promptlab.api:app --host 127.0.0.1 --port 8000 --workers 1

frontend:
	cd frontend && npm run dev

test:
	python -m pytest
