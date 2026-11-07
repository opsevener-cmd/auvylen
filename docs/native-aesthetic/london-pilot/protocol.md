# London Set feasibility protocol — fixed before model fitting, 2026-11-01

Decision: GO for a private, non-commercial scientific feasibility study using the
Face Research Lab London Set; NO-GO for public/commercial service activation.
Dataset: DeBruine & Jones (2017), Version 5, DOI 10.6084/m9.figshare.5047666.v5.
Use only the 102 adult neutral frontal photographs from the authors' official
`debruine/webmorphR.stim` repository, commit fa8b78fda2d659bb74ce62fcd99c4407551d2a77.
Annotations and subject metadata: authors' `debruine/demopsydata`, commit
1b5d2a179edd873162a54dec11faff2163afe6c0, original London CSV files.

The dataset record and authors' image-set README designate these photographs and
ratings CC BY 4.0 and report signed subject consent for lab/web research. CC BY 4.0
permits copying/adaptation with attribution, including computational research;
privacy/publicity rights are not supplied by that copyright licence. Published
research consent supports this closed feasibility study, not an assertion that
participants endorsed a consumer/commercial face-scoring service. No model weights,
photos, individual ratings, individual predictions or demographic rows will be
published. Existing MobileNet rights remain non-commercial research only.

Inclusion: official neutral frontal image inventory; subject metadata confirms age
>=18. Only existing rater records with a finite age >=18 contribute to mean ratings.
Retain source ratings on their native 1–7 scale (no 1–5 or 1–10 conversion). Missing
ratings are omitted independently per portrait; require >=3 genuine adult ratings.
Join images/metadata/ratings by official pseudonymous ID; never infer identity or age.

Freeze seed 42 with existing subject-hash 60/20/20 partitions before model selection.
Each subject has one neutral frontal photograph; no profile/smile images enter fitting.
Compare handcrafted RGB/texture and the already verified MobileNetV3-Small embeddings.
For each, ridge alpha candidates are exactly .01, 1, 100. Fit train-only statistics
and train augmentation (brightness .85, central 90% crop); validation MAE determines
one encoder/alpha winner. No new hyperparameters, seeds or architectures will be
chosen from the test result. Report both encoders' already validation-selected heads
on the same sealed test split, plus train-mean and train-median baselines.

Report native-scale MAE/RMSE/Spearman, paired model-minus-mean MAE, and percentile 95%
subject bootstrap intervals (2000 samples; seed 20261101). This small holdout is a
feasibility estimate, not a population validation. Report declared gender, age-band
and ethnicity subgroup counts; suppress performance/interval estimates for n<5.
Do not infer demographics. Compare controlled lighting/crop/rotation drift against
original images; altered images have no new human labels and in-plane rotation is
not a yaw/pitch study. Genuine pose robustness remains unvalidated.

Measure a private saved checkpoint's CPU cold load, warm complete portrait prediction,
peak RSS and model bytes after byte/hash verification and reload prediction parity.
Research inspection may load an unreleased head through the explicit offline inspection
function; product NativeEngine/NativeProvider release gates must continue refusing it.
No API route, live database, participant collection/contact, payments or deployment.
No claims about facial symmetry, health, worth or objective beauty.
