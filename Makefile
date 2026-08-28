PYTHON ?= python3

.PHONY: setup sample score test clean
setup:
	$(PYTHON) -m pip install -r requirements.txt

sample:
	$(PYTHON) baseline_naive_rag.py \
		--questions eval/sample_questions.json \
		--round-id sample \
		--output outputs/submission_sample.json \
		--rebuild

score:
	$(PYTHON) score_submission.py \
		--submission outputs/round1/submission_round_1_pre_opt.json \
		--annotations eval/annotations_round_1.json

test:
	$(PYTHON) -m pytest -q

clean:
	rm -rf outputs/qdrant outputs/submission_*.json .pytest_cache __pycache__ tests/__pycache__
