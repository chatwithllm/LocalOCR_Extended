# Token build targets.
# Requires: python3 with ruamel.yaml installed. Activate .venv-tokens first
# (`source .venv-tokens/bin/activate`) or set PYTHON=path/to/venv/python3.

PYTHON ?= python3

.PHONY: tokens tokens-check fonts

# Regenerate all token artefacts (CSS, Dart, fonts sidecar, pubspec fonts block).
tokens:
	$(PYTHON) scripts/build_tokens.py --target all
	$(PYTHON) scripts/merge_fonts_into_pubspec.py

# CI gate: regenerate, then assert nothing changed.
tokens-check: tokens
	git diff --exit-code -- \
	  src/frontend/styles/tokens.generated.css \
	  lib/app/theme/tokens.generated.dart \
	  tool/fonts.generated.yaml \
	  pubspec.yaml

# Just merge fonts (use when only fonts.generated.yaml changed).
fonts:
	$(PYTHON) scripts/merge_fonts_into_pubspec.py
