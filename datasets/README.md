# Synthetic ticket suite

200 fixtures: four categories × five base phrasings × ten context variations.
Half contain an explicit urgent marker. Expected outputs are category and priority
JSON objects. The mock adapter uses keyword rules and never receives expected
labels. These fixtures exercise the pipeline; repeated phrasings are correlated
and are not a representative real-world accuracy benchmark.

Dataset bytes are hashed into every run. Baseline comparison requires the same
dataset hash, prompt name, provider kind, and model. Edit this file to introduce
real, reviewed examples; changed data requires a fresh baseline.
