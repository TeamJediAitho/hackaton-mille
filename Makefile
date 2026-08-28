PYTHON ?= python3

.PHONY: setup sample score regression test clean
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

# Set di regressione della Fase 1: ricostruisce act 1+2 in una collection separata e misura le
# stesse 8 domande del round 1. Soglie dichiarate nel piano: recall@5 >= 0,952 e MRR >= 0,886.
# Niente --baseline: submission_round_1_post_opt.json non e' su disco (outputs/ e' gitignorato) e
# nessuna submission archiviata riproduce MRR 0,886 - si misura contro le soglie assolute.
regression:
	$(PYTHON) baseline_naive_rag.py \
		--questions eval/questions_round_1.json \
		--round-id round_1 \
		--act 1 2 \
		--qdrant-path outputs/qdrant_act12 \
		--output outputs/round1/regressione_act12.json \
		--rebuild
	$(PYTHON) score_submission.py \
		--submission outputs/round1/regressione_act12.json \
		--annotations eval/annotations_round_1.json \
		--verify-contexts

test:
	$(PYTHON) -m pytest -q

clean:
	rm -rf outputs/qdrant outputs/qdrant_act12 outputs/submission_*.json .pytest_cache __pycache__ tests/__pycache__
