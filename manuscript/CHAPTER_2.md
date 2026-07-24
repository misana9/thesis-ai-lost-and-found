# CHAPTER 2
# REVIEW OF RELATED LITERATURE

## 2.1 Introduction

This chapter reviews related literature and studies that situate the present investigation on an AI-powered lost-and-found matching algorithm using image embedding generation and semantic similarity analysis. The review was assembled topically rather than chronologically, following the guidance that related literature should be organized by theme irrespective of local or foreign origin (Zulueta, 2010). Consistent with a funnel organization (Lunenburg, 2008), the discussion moves from broad institutional recovery problems toward digital reporting systems, then toward vision–language matching and ranked retrieval policies most closely related to FindIt.

The chapter is organized under the following headings: Challenges of Conventional Campus Item Recovery; Digital Lost-and-Found Reporting Platforms; Contrastive Vision–Language Models for Image–Text Matching; Ranked Semantic Retrieval for Noisy User Queries; and Synthesis of the Reviewed Literature. The synthesis identifies shared themes, points of divergence, and the research gap addressed by the present study.

## 2.2 Challenges of Conventional Campus Item Recovery

University lost-and-found practice has historically depended on counter logs, verbal identification, and physical storage. Mullins and Lee (2017) documented how inconsistent documentation and frequent misidentification reduce recovery reliability in campus settings. When formal channels are weak, communities often improvise. Tan and Chong (2023), in a campus survey setting, observed that many students and staff announce losses through WhatsApp or Facebook. Those informal posts offered limited reach, weak search structure, and insufficient ownership verification, occasionally enabling false claims. Scheduling conflicts further reduced the chance that owners could repeatedly follow up in person, prompting the authors to call for formal systems that support categorized reporting and search.

Parallel problems appear in office-side recordkeeping. Castro et al. (2022) described how manual logs can become disorganized, expose sensitive information, and slow validation when claimants arrive. Alston (2022) likewise noted that handwritten records complicate recovery and limit traceability, while Nadeem et al. (2022) emphasized the personal stress associated with losing valued belongings. Collectively, these studies establish the service problem that motivates FindIt: recovery fails not only because items are missing, but because institutions lack dependable mechanisms for comparing heterogeneous evidence at scale.

## 2.3 Digital Lost-and-Found Reporting Platforms

Digitization improved intake and visibility. Kim et al. (2019) and Gupta and Sharma (2020) presented web-oriented lost-and-found tools that log found items and support search by category or description. Accessibility increased, yet pairing often remained dependent on human verification and basic keyword filters. Castro et al. (2022) further examined AUFound, a campus platform in which students submit reports through a mobile application while administrators manage claims through a web interface, with categorized listings and messaging for timely notices. Organization improved, but match verification still relied substantially on staff review.

Other campus-oriented builds reinforce the same pattern. Pandey et al. (2020) developed a web platform for college lost-and-found workflows with centralized reporting, search, claim handling, dashboards, and email notifications, addressing inefficiencies of bulletin boards and physical logs. Shrivastava et al. (2025) proposed a modern web architecture supporting image uploads, authentication, notifications, and structured item records, reporting faster recovery and higher matching success relative to manual baselines. Salman (2022) highlighted registration, reporting, and direct communication between finder and owner once a candidate relationship is known.

These platforms supply durable design lessons for FindIt: structured tickets, media attachments, and notifications matter. Their recurring ceiling is the matching engine. Keyword browsing and staff-mediated pairing do not scale cleanly when descriptions diverge or when photographs carry most of the identity signal. The present study therefore treats digital ticketing as necessary infrastructure and concentrates research effort on multimodal embedding ranking between submission and confirmation.

## 2.4 Contrastive Vision–Language Models for Image–Text Matching

Cross-modal retrieval research shows that contrastive vision–language training can place related images and captions near one another so cosine similarity becomes a meaningful relevance score. Peng (2025) developed a CLIP-based matching approach using Vision Transformer image encoding and text encoding aligned through contrastive learning. On curated image–text pairs, reported Recall@K values were strong, and the work outperformed an earlier baseline by a substantial margin on top-rank retrieval. Those results support the feasibility of comparing a found photograph with a lost description inside one representation space.

Related CLIP research clarifies both opportunity and constraint. Li et al. (2022) introduced DeCLIP to improve data efficiency through additional supervision signals, showing that robust multimodal representations can be obtained under more constrained data regimes and examining ViT-B/32 among other encoders. Xie et al. (2023) proposed RA-CLIP to expose models to harder negatives through retrieval augmentation, while Pan et al. (2022) enriched CLIP-style learning with structured knowledge. Fang et al. (2022) found that training-distribution diversity was a primary driver of robustness under shift, and Cui et al. (2022) provided benchmarking evidence that data quality and supervision choices materially affect zero-shot behavior across architectures. Dong et al. (2026) further cautioned that a single global image embedding may miss fine-grained cues in complex scenes and proposed multi-slot representations with adaptive fusion, improving R@1 over standard CLIP on established retrieval benchmarks.

For institutional lost-and-found use, this body of work justifies CLIP ViT-B/32 as FindIt’s embedding backbone. It also warns against treating raw cosine scores as final authority. Campus tickets are noisy, look-alike objects are common, and user descriptions are short. Application-level fusion, thresholds, and human confirmation are therefore necessary complements to the pretrained encoder. Unlike approaches that separate image matching and text matching into unrelated embedding spaces, FindIt keeps image and text comparison inside CLIP’s shared multimodal space so cross-modal pairs remain directly comparable.

Zhou et al. (2023) illustrated a related applied direction through LostNet, a lightweight deep learning system for recognizing lost items in other service environments. Although not a campus ticket matcher, the study reinforces that visual recognition can reduce manual labor in recovery workflows and supports the broader move toward AI-assisted item identification.

## 2.5 Ranked Semantic Retrieval for Noisy User Queries

Dense embedding retrieval research emphasizes nearest-neighbor comparison and the practical value of returning an ordered top-k list when queries are ambiguous (Muennighoff et al., 2022). Short-text semantic similarity literature likewise documents lexical sparsity, polysemy, and limited context as persistent challenges for user-authored phrases (Amur et al., 2023). Lost-and-found submissions inherit those difficulties: owners and finders may describe the same object differently, omit details, or rely primarily on photographs taken under uneven conditions.

Under such conditions, a single irreversible top-1 decision is brittle. Ranked retrieval with confidence filtering better matches operational risk control. Correct items that appear at rank two or three can still be recovered if the interface preserves an ordered shortlist and requires confirmation before claim closure. That policy aligns with evaluation practices that report not only Precision@1 but also hit rate at small k and mean reciprocal rank. FindIt adopts this stance by discarding weak scores, ranking survivors, presenting a trimmed shortlist, and finalizing links only after confirmation-centered claim actions.

## 2.6 Synthesis of the Reviewed Literature

### 2.6.1 Emerging Themes

Across the reviewed works, three themes recur. First, conventional and informal recovery channels are unreliable under volume and ambiguity. Second, digital ticket platforms improve submission, organization, and notification yet often leave comparison to keywords or staff judgment. Third, contrastive vision–language models provide a principled mechanism for image–text similarity, while ranked retrieval theory explains how to present imperfect but useful candidate lists under noisy queries.

### 2.6.2 Points of Divergence

The literature diverges in where automation stops. Some systems digitize intake only. Others advance CLIP-style retrieval on general benchmarks without embedding that retrieval in campus claim workflows. Methodological choices also differ: keyword search versus learned embeddings, top-1 automatic linking versus ranked shortlists, and cross-modal unified spaces versus separate unimodal pipelines. FindIt differs by integrating CLIP-based multimodal scoring, adaptive fusion, thresholded ranking, bidirectional ticket search, and confirmation-triggered coordination inside one institutional prototype.

### 2.6.3 Research Gap and Positioning of the Present Study

Despite progress, a practical gap remains. Few campus-oriented systems fully operationalize multimodal embedding ranking for noisy lost-and-found tickets while preserving human confirmation before notification and status closure. General CLIP studies validate cross-modal retrieval but do not fully specify institutional policies such as confidence tiers, shortlist trimming, bidirectional matching on report submission, and claim lifecycle handling.

The present study addresses that gap through FindIt: ticket capture, CLIP ViT-B/32 embedding generation, multimodal semantic similarity ranking, ordered user choice, and confirmation-centered email coordination. In doing so, the review supports both the problem framing in Chapter 1 and the technical design presented in Chapter 3, and it points toward evaluation methods that measure early-rank retrieval quality together with end-to-end claim behavior.

