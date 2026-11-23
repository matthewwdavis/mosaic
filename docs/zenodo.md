# A DOI for each release (Zenodo)

Zenodo gives each mosaic release a DOI, a permanent link that journals accept in a reference list.
Once it's switched on, every release made with `python tools/release.py publish` gets one by itself.
Zenodo reads `.zenodo.json` (title, description, author, licence) for the record; `CITATION.cff` is
what GitHub's **Cite this repository** button and mosaic's **Help ▸ Cite mosaic** read.

## Matthew's one-time steps

1. Go to <https://zenodo.org> and click **Log in**, then **Log in with GitHub**, and allow it.
2. Open your name (top right) ▸ **GitHub**. Find **matthewwdavis/mosaic** in the list of
   repositories (click **Sync now** if it isn't there) and switch it **On**.
3. Make the next release as usual. A few minutes later it shows on that GitHub page in Zenodo with
   a DOI badge. Zenodo makes two DOIs: one for that release, and a "concept" DOI that always leads
   to the newest release. The concept DOI is the one to cite in general.
4. Then ask Claude to add the DOI: it goes in `CITATION.cff` and its copy in `mosaic/data/CITATION.cff`
   (`doi: 10.5281/zenodo.NNNNNNN`), and in the README's "How to cite" (the reference and the BibTeX
   then end with the DOI instead of the GitHub link). Help ▸ Cite mosaic picks it up from there.

Zenodo only lists public repositories; mosaic's is public.

## Later

- **Your ORCID:** add it under the author in `CITATION.cff` (and its copy) as
  `orcid: "https://orcid.org/0000-0000-0000-0000"`, and in `.zenodo.json` as
  `"orcid": "0000-0000-0000-0000"` beside the name.
- **Another author:** add them to the `authors` list in `CITATION.cff` (and its copy) and to
  `creators` in `.zenodo.json`.
- The version and date in `CITATION.cff` are set by each release; don't change them by hand.
