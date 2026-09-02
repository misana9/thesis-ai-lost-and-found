# CHAPTER 2
# REVIEW OF RELATED LITERATURE

## 2.1 Introduction

This chapter reviews related literature and studies that situate the present investigation on an AI-powered lost-and-found matching algorithm using image embedding generation and semantic similarity analysis. The review was assembled both thematically and by geographic origin. Following Zulueta (2010), conceptual literature is organized by theme irrespective of local or foreign source. Consistent with a funnel organization (Lunenburg, 2008), the discussion moves from broad institutional recovery problems toward digital reporting systems, then toward vision–language matching and ranked retrieval policies most closely related to AMAlost. Dedicated sections then summarize **local related studies** (Philippine settings) and **foreign related studies** (settings outside the Philippines) so that the institutional and technical precedents for AMAlost are explicit.

The chapter is organized under the following headings: Challenges of Conventional Campus Item Recovery; Digital Lost-and-Found Reporting Platforms; Contrastive Vision–Language Models for Image–Text Matching; Technical Background (Cosine Similarity and Adaptive Multimodal Fusion); Ranked Semantic Retrieval for Noisy User Queries; Local Related Studies; Foreign Related Studies; and Synthesis of the Reviewed Literature. The synthesis identifies shared themes, points of divergence, and the research gap addressed by the present study.

## 2.2 Challenges of Conventional Campus Item Recovery

University lost-and-found practice has historically depended on counter logs, verbal identification, and physical storage. Mullins and Lee (2017) documented how inconsistent documentation and frequent misidentification reduce recovery reliability in campus settings. When formal channels are weak, communities often improvise. Tan and Chong (2023), in a campus survey setting, observed that many students and staff announce losses through WhatsApp or Facebook. Those informal posts offered limited reach, weak search structure, and insufficient ownership verification, occasionally enabling false claims. Scheduling conflicts further reduced the chance that owners could repeatedly follow up in person, prompting the authors to call for formal systems that support categorized reporting and search.

Parallel problems appear in office-side recordkeeping. Castro et al. (2022) described how manual logs can become disorganized, expose sensitive information, and slow validation when claimants arrive. Alston (2019; 2022) likewise noted that handwritten records complicate recovery and limit traceability in campus offices, including Philippine university contexts referenced in later local systems research. Nadeem et al. (2022) emphasized the personal stress associated with losing valued belongings. Collectively, these studies establish the service problem that motivates AMAlost: recovery fails not only because items are missing, but because institutions lack dependable mechanisms for comparing heterogeneous evidence at scale.

## 2.3 Digital Lost-and-Found Reporting Platforms

Digitization improved intake and visibility. Kim et al. (2019) and Gupta and Sharma (2020) presented web-oriented lost-and-found tools that log found items and support search by category or description. Accessibility increased, yet pairing often remained dependent on human verification and basic keyword filters. Castro et al. (2022) further examined AUFound, a Philippine campus platform in which students submit reports through a mobile application while administrators manage claims through a web interface, with categorized listings and messaging for timely notices. Organization improved, but match verification still relied substantially on staff review.

Other campus-oriented builds reinforce the same pattern. Pandey et al. (2020) developed a web platform for college lost-and-found workflows with centralized reporting, search, claim handling, dashboards, and email notifications, addressing inefficiencies of bulletin boards and physical logs. Shrivastava et al. (2025) proposed a modern web architecture supporting image uploads, authentication, notifications, and structured item records, reporting faster recovery and higher matching success relative to manual baselines. Salman (2022) highlighted registration, reporting, and direct communication between finder and owner once a candidate relationship is known.

These platforms supply durable design lessons for AMAlost: structured tickets, media attachments, and notifications matter. Their recurring ceiling is the matching engine. Keyword browsing and staff-mediated pairing do not scale cleanly when descriptions diverge or when photographs carry most of the identity signal. The present study therefore treats digital ticketing as necessary infrastructure and concentrates research effort on multimodal embedding ranking between submission and confirmation.

## 2.4 Contrastive Vision–Language Models for Image–Text Matching

Cross-modal retrieval research shows that contrastive vision–language training can place related images and captions near one another so cosine similarity becomes a meaningful relevance score. Radford et al. (2021) introduced CLIP (Contrastive Language–Image Pre-training), demonstrating that a joint embedding space learned from large-scale image–text pairs enables zero-shot transfer across vision tasks and supports direct image–text comparison. That foundation is central to AMAlost’s decision to encode campus tickets with a pretrained CLIP ViT-B/32 encoder rather than maintaining separate, non-aligned vision and keyword pipelines.

Peng (2025) developed a CLIP-based matching approach using Vision Transformer image encoding and text encoding aligned through contrastive learning. On curated image–text pairs, reported Recall@K values were strong, and the work outperformed an earlier baseline by a substantial margin on top-rank retrieval. Those results support the feasibility of comparing a found photograph with a lost description inside one representation space.

Related CLIP research clarifies both opportunity and constraint. Li et al. (2022) introduced DeCLIP to improve data efficiency through additional supervision signals, showing that robust multimodal representations can be obtained under more constrained data regimes and examining ViT-B/32 among other encoders. Xie et al. (2023) proposed RA-CLIP to expose models to harder negatives through retrieval augmentation, while Pan et al. (2022) enriched CLIP-style learning with structured knowledge. Fang et al. (2022) found that training-distribution diversity was a primary driver of robustness under shift, and Cui et al. (2022) provided benchmarking evidence that data quality and supervision choices materially affect zero-shot behavior across architectures. Dong et al. (2026) further cautioned that a single global image embedding may miss fine-grained cues in complex scenes and proposed multi-slot representations with adaptive fusion, improving R@1 over standard CLIP on established retrieval benchmarks.

Recent applied lost-and-found architectures likewise extend CLIP rather than replace it. Cascaded designs that combine object detection (for example, YOLO), optional large-language-model description refinement, and CLIP retrieval have been proposed to mitigate CLIP’s weakness on cluttered backgrounds by first isolating candidate objects before embedding (IEEE IRCE, 2025). ComCLIP (Jiang et al., 2024) similarly argues that compositional mismatches can fool global CLIP matching and proposes training-free decomposition strategies. For institutional lost-and-found use, this body of work justifies CLIP ViT-B/32 as AMAlost’s embedding backbone while warning against treating raw cosine scores as final authority. Campus tickets are noisy, look-alike objects are common, and user descriptions are short. Application-level fusion, thresholds, and human confirmation are therefore necessary complements to the pretrained encoder.

Zhou et al. (2024) illustrated a related applied direction through LostNet, a lightweight deep learning system for recognizing lost items in other service environments. Although not a campus ticket matcher, the study reinforces that visual recognition can reduce manual labor in recovery workflows and supports the broader move toward AI-assisted item identification.

## 2.5 Technical Background: Cosine Similarity and Adaptive Multimodal Fusion

The matching literature reviewed above assumes a formal similarity measure between embeddings. Let \(\mathbf{a}, \mathbf{b} \in \mathbb{R}^{512}\) be L2-normalized CLIP vectors (image or text). Cosine similarity reduces to an inner product:

\[
\operatorname{sim}(\mathbf{a},\mathbf{b})
= \mathbf{a}^{\top}\mathbf{b}
= \frac{\mathbf{a}\cdot\mathbf{b}}{\|\mathbf{a}\|\,\|\mathbf{b}\|}.
\]

Values near \(1\) indicate stronger semantic relatedness; values near \(0\) indicate weak relatedness in the shared space.

Because a lost–found ticket pair may supply image, text, or both, a single modality score is insufficient. AMAlost therefore uses **adaptive multimodal fusion**: available pairwise cosines are combined with weights that depend on which signals exist. Denote

- \(s_{ii}\): image-to-image cosine,
- \(s_{ti}\): lost-text to found-image cosine,
- \(s_{ftli}\): found-text to lost-image cosine.

Text-to-text cosine may be computed for interface transparency but is **excluded** from the ranked score, because generic category words (e.g., both tickets saying “calculator”) can inflate lexical agreement without establishing item identity.

**Table. Adaptive fusion cases**

| Available modalities | Fusion formula |
|---|---|
| Image + lost-text + found-text cross | \(s_{\mathrm{raw}} = 0.60\,s_{ii} + 0.25\,s_{ti} + 0.15\,s_{ftli}\) |
| Image + lost-text only | \(s_{\mathrm{raw}} = 0.75\,s_{ii} + 0.25\,s_{ti}\) |
| Image + found-text cross only | \(s_{\mathrm{raw}} = 0.85\,s_{ii} + 0.15\,s_{ftli}\) |
| Single available modality | \(s_{\mathrm{raw}} = s_{ii}\) or \(s_{\mathrm{raw}} = s_{ti}\) |

Contextual adjustment:

\[
s' = s_{\mathrm{raw}} \cdot
\begin{cases}
1.10 & \text{same category}\\
0.75 & \text{otherwise}
\end{cases}
+ \mathbb{1}_{\mathrm{loc}}\,0.06 + \delta_{\mathrm{time}},
\qquad
s_{\mathrm{final}} = \min(s', 0.99).
\]

**Table. Confidence tiers on \(s_{\mathrm{final}}\)**

| Tier | Cutoff | Role |
|---|---|---|
| Strong | \(s_{\mathrm{final}} \ge 0.85\) | High-precision band |
| Possible | \(s_{\mathrm{final}} \ge 0.70\) | Balanced shortlist |
| Weak | \(s_{\mathrm{final}} \ge 0.55\) | Minimum inclusion / recall floor |
| Drop | \(s_{\mathrm{final}} < 0.55\) | Excluded from UI shortlist |

(If informal discussion refers to “dynamic wave fusion,” that phrase maps to this adaptive weighted fusion of modality cosines.) Chapter 3 restates these equations in the algorithms section and links them to implementation.

## 2.6 Ranked Semantic Retrieval for Noisy User Queries

Dense embedding retrieval research emphasizes nearest-neighbor comparison and the practical value of returning an ordered top-k list when queries are ambiguous (Muennighoff et al., 2022). Short-text semantic similarity literature likewise documents lexical sparsity, polysemy, and limited context as persistent challenges for user-authored phrases (Amur et al., 2023). Lost-and-found submissions inherit those difficulties: owners and finders may describe the same object differently, omit details, or rely primarily on photographs taken under uneven conditions.

Under such conditions, a single irreversible top-1 decision is brittle. Ranked retrieval with confidence filtering better matches operational risk control. Correct items that appear at rank two or three can still be recovered if the interface preserves an ordered shortlist and requires confirmation before claim closure. That policy aligns with evaluation practices that report not only Precision@1 but also hit rate at small k and mean reciprocal rank. AMAlost adopts this stance by discarding weak scores, ranking survivors, presenting a trimmed shortlist, and finalizing operational closure only after confirmation and staff desk custody.

## 2.7 Local Related Studies

Local related studies refer to Philippine institutional projects and publications that digitize campus lost-and-found operations. Across these works, the dominant contribution is structured reporting, admin oversight, and status tracking. Automated multimodal matching is largely absent—an important gap for AMAlost.

**Castro, David, De Silva, Roxas, and Macaspac (2022)** developed **AUFound** for Angeles University Foundation (Pampanga). Students report misplaced belongings through a mobile application, while administrators manage claimed, unclaimed, due, and donated items through a web interface with search filters and messaging. Survey evaluation using a 7-point Likert scale indicated that the system improved awareness, record accuracy, and replacement of error-prone manual logbooks. Matching and claim verification, however, remained staff-mediated rather than embedding-driven.

**Armada and Milanio (2021)** presented **GC Found It**, a web and mobile application for Gordon College lost-and-found processing using a progressive framework. The system centralized lost and found posting, allowed administrators to monitor user posts and post found items, and positioned the administrator as the channel for returning claimed property. The study underscores convenience and security of digital reporting for Philippine college stakeholders, while still depending on human review to decide ownership and return.

**Ballard, Caw-it, Daig, Lasagas, Pabatang, and Sumaylo (2025)** implemented the **USTP Panaon Lost and Found Management System** at the University of Science and Technology of Southern Philippines–Panaon. The system combines a mobile/web application with QR-code identification, a centralized database, and role-based dashboards. ISO/IEC 25010-oriented evaluation yielded “Very Good” to “Excellent” ratings for functionality, usability, efficiency, and related quality attributes. The project modernizes tracking and communication but does not employ CLIP-style semantic image–text ranking.

**Researchers at the Polytechnic University of the Philippines** developed **PUP-BARK (Belongings and Recovery Kiosk)**, a campus lost-and-found web application intended to help security personnel manage surrendered items and allow constituents to browse found listings. Documented features include category/location/date filtering, photo-supported item details, claim-form submission, and status tracking (claimed/unclaimed). Like other local portals, BARK strengthens intake and custody workflows; similarity search remains filter- and staff-oriented.

**A Mindanao State University–Sulu BS Information Technology capstone project** proposed the **MSU-Sulu Lost and Found Monitoring and Management System and Application** to replace the absence of a dedicated campus recovery platform. Planned capabilities include report logging with descriptions and images, centralized storage, notifications when a related found item appears, identity verification to reduce fraudulent claims, and an administrator dashboard. The project illustrates the Philippine demand for digital recovery services outside Metro Manila, again with emphasis on repository and notification design rather than multimodal embedding ranking.

**A Cebu Technological University–Bantayan Information Technology project** likewise designed a **Lost and Found Management System** for campus members to report and manage lost and found records through authenticated web workflows (create, read, update, delete, and search). The documented scope highlights automation of previously manual campus transactions and offline operational constraints in some versions. The contribution is operational digitization; intelligent cross-modal matching is outside its focus.

Taken together, local studies confirm that Philippine campuses need centralized, authenticated, image-capable ticketing and admin queues. They also show that current local solutions generally stop at keyword or staff pairing. AMAlost builds on that local infrastructure agenda by adding CLIP-based multimodal ranking and confirmation-centered claim closure.

## 2.8 Foreign Related Studies

Foreign related studies provide both campus portal precedents outside the Philippines and the multimodal retrieval science that AMAlost adapts.

**Radford et al. (2021)** introduced CLIP at OpenAI, showing that contrastive pretraining on hundreds of millions of image–text pairs yields a shared embedding space in which cosine similarity supports zero-shot recognition and cross-modal retrieval. AMAlost relies on this pretrained mechanism (ViT-B/32) as the starting encoder and additionally applies light campus fine-tuning on Objects photographs so that domain-specific item views can further adapt the visual representation used in matching.

**Tan and Chong (2023)** designed and evaluated **FoundeLost**, a web and mobile lost-and-found service for Universiti Kebangsaan Malaysia (UKM). Users can post lost or found items with location details and images, authenticate with matric/contact information, and use security questions to reduce fraud; items held beyond a month can be auto-disposed. Their campus survey documented heavy dependence on informal social channels and motivated a formal categorized system. Matching remains listing- and filter-based rather than embedding-ranked.

**Zhou et al. (2024)** proposed **LostNet**, integrating an attention-enhanced MobileNetV2 classifier with perceptual hashing inside a Spring Boot web framework for lost-item image identification. Reported test accuracy reached 96.8% with a lightweight compute footprint suitable for ordinary laptops. LostNet demonstrates that visual AI can accelerate recovery workflows, though its pipeline is closer to image recognition/hash matching than to CLIP’s joint image–text embedding space used in AMAlost.

**Adelowo, Ndukuba, Adebiyi, and Falaye (2026)** implemented an online lost-and-found portal for **Babcock University** (Nigeria) using React/TypeScript and Supabase (PostgreSQL, JWT auth, storage, real-time). Features included image uploads, full-text keyword search, claim/notification flows, user dashboards, and admin claim verification. Functional testing, SUS usability scoring (83.4), and performance audits supported the portal’s practicality. Search remains keyword-centered, reinforcing AMAlost’s distinct contribution in multimodal ranking.

**Walpita Gamage (2026)** developed a centralized web-based lost-and-found management system for **Häme University of Applied Sciences (HAMK)** in Finland to replace information-desk manual processes. The prototype included registration/login, lost and found forms, guest access, community feed with search/filter, image upload, and an administrative dashboard, implemented with HTML/CSS/JavaScript/PHP. The study explicitly contrasts traditional, web-based, and AI-capable approaches and positions centralized digital intake as the immediate institutional need—again leaving advanced multimodal matching as future work relative to AMAlost’s focus.

**Peng (2025)** and related CLIP retrieval studies (Section 2.4) further establish that Vision Transformer–based contrastive encoders can achieve strong Recall@K on image–text benchmarks. **Muennighoff et al. (2022)** and short-text similarity surveys (Amur et al., 2023) justify returning ranked shortlists under ambiguous queries rather than irreversible top-1 automation. Collectively, foreign studies supply AMAlost’s AI backbone and ranking policy while showing that many international campus portals still stop at digitization and keyword search.

## 2.9 Synthesis of the Reviewed Literature

### 2.9.1 Emerging Themes

Across the reviewed works, three themes recur. First, conventional and informal recovery channels are unreliable under volume and ambiguity. Castro et al. (2022) describe handwritten campus logs that become disorganized and slow to validate, while Tan and Chong (2023) document heavy student dependence on WhatsApp and Facebook posts that are weakly searchable and weakly verified. Second, digital ticket platforms improve submission, organization, and notification, yet often leave comparison to keywords or staff judgment. This pattern appears in local systems such as AUFound by Castro, David, De Silva, Roxas, and Macaspac (2022), GC Found It by Armada and Milanio (2021), the USTP Panaon system documented by Lasagas et al. (2025) / Ballard et al. (2025), and See You in CEU by Quitlong, Escalante, Bernardino, and Ayo (2026), as well as foreign portals such as FoundeLost by Tan and Chong (2023) and the Babcock University system by Adelowo, Ndukuba, Adebiyi, and Falaye (2026). Third, contrastive vision–language models and ranked retrieval theory provide a principled way to compare photos and text under noise: Radford et al. (2021) establish CLIP’s shared embedding space and cosine similarity; Muennighoff et al. (2022) justify ordered top-*k* shortlists for ambiguous queries; and Amur et al. (2023) explain why short user phrases are sparse and unreliable for keyword-only matching. Zhou et al. (2024) further show that visual AI (LostNet) can assist recovery, though through a recognition/hash pipeline rather than joint CLIP image–text ranking.

### 2.9.2 Points of Divergence

The literature diverges in where automation stops. Local Philippine studies such as Castro et al. (2022), Armada and Milanio (2021), and Lasagas et al. (2025) primarily digitize intake, status tracking, and admin oversight. Quitlong et al. (2026) add CNN-based keyword extraction but still end in keyword matching. Foreign campus portals by Tan and Chong (2023) and Adelowo et al. (2026) likewise stop at listing, filters, or keyword search. Zhou et al. (2024) advance image recognition for lost items, while Radford et al. (2021), Muennighoff et al. (2022), and Amur et al. (2023) validate cross-modal embeddings and ranked shortlists without specifying full campus claim workflows. Mayor, Real, and Saturno (2026) extend automation further through SafeKeep’s CLIP-related matching plus IoT smart-locker custody, whereas software-only portals stop at reporting and search. Methodological choices therefore differ: keyword search versus learned embeddings, top-1 automation versus ranked shortlists, cross-modal unified spaces versus separate pipelines, and locker-mediated handoff versus confirmation-centered digital claims. AMAlost differs by integrating CLIP-based multimodal scoring, adaptive fusion, thresholded ranking, bidirectional ticket search, and confirmation-triggered coordination inside one institutional software prototype.

### 2.9.3 Research Gap and Positioning of the Present Study

Despite this progress, a practical gap remains. Few campus-oriented systems fully operationalize multimodal embedding ranking for noisy lost-and-found tickets while preserving human confirmation before notification and status closure. SafeKeep by Mayor, Real, and Saturno (2026) demonstrates CLIP-related matching with IoT lockers, but does not specify the present study’s locker-free software policies—confidence tiers, shortlist trimming, bidirectional matching on report submission, light campus fine-tuning, and confirmation plus staff desk custody. Foundational CLIP and retrieval studies by Radford et al. (2021), Muennighoff et al. (2022), and Amur et al. (2023) validate the matching mechanism, while local digitization studies by Castro et al. (2022), Armada and Milanio (2021), Lasagas et al. (2025), and Quitlong et al. (2026) validate the institutional need; the missing combination is an institutional workflow that joins both.

The present study addresses that gap through AMAlost: ticket capture, CLIP ViT-B/32 embedding generation with light campus fine-tuning, multimodal semantic similarity ranking, ordered user choice, confirmation-centered notifications, and staff desk custody for exchange. In doing so, the review supports both the problem framing in Chapter 1 and the technical design presented in Chapter 3, and it points toward evaluation methods that measure early-rank retrieval quality together with end-to-end claim and desk behavior.
