dmsvg - Doom map SVG renderer
by Revenant

dmvis is a Python 3.x script to make top-down SVG renders of Doom engine levels. Maps are rendered "to scale" with correctly sized/aligned floor textures and approximate light levels for each sector.

See the "examples" directory for some example output for maps from Ultimate Doom and Doom II.

Known issues:
* Sectors must be properly closed in order for the script to process them correctly. Rendering a map that mistakenly includes non-closed sectors (such as E1M3 or E4M1) will most likely cause these sectors to be drawn incorrectly.

dmsvg uses the "omgifol" library to load maps. The current version can be obtained by running `pip install omgifol`. The Pillow library is also used for converting flats.
