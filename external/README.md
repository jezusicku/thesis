# External references

This folder is for **optional third-party clones** used only as **bibliographic / algorithmic reference**, not as runtime dependencies.

- **[ER-Wikidata-WF](https://github.com/luizdovalle2/ER-Wikidata-WF)** — entity resolution on Wikidata. This project borrows the **idea** of combining text similarity with **phonetic** agreement (e.g. Daitch–Mokotoff); the code lives in `annotator/phonetic_polish.py` and `matchers/phonetic_wikidata.py`.

To clone locally (not required to run the app):

```bash
git clone https://github.com/luizdovalle2/ER-Wikidata-WF.git external/ER-Wikidata-WF
```

The path `external/ER-Wikidata-WF/` is listed in `.gitignore` so it is not committed.
