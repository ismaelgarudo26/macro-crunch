# macro-crunch

A small Python macro-nutrient calculator. Snap a photo of your fridge and a screenshot of your remaining
macros, and it proposes a meal that fits. An LLM picks ingredients and gram amounts, and plain Python does
all the math and checks the fit.

Work in progress: the core logic and model calls work, but there's no app or UI yet.

## Setup

Requires Python 3.10+ and an [OpenAI API key](https://platform.openai.com/api-keys).

```bash
git clone https://github.com/ismaelgarudo26/macro-crunch.git
cd macro-crunch

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Then copy `.env.example` to `.env` and paste your key after `OPENAI_API_KEY=`. `.env` is gitignored.

## Run the tests

```bash
python -m pytest -v
```

The tests use a fake OpenAI client, so they need no API key or network access.

## Try it

```python
from pathlib import Path
from macro_crunch import vision, verify

available = vision.extract_ingredients(Path("fridge.jpg").read_bytes())
remaining = {"cal": 600, "protein": 40, "carbs": 60, "fat": 20}

result = verify.run_loop(available, remaining)
print(result.status, result.meal)
```
