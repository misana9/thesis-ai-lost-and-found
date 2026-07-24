# CHAPTER 1
# INTRODUCTION

## 1.1 Background of the Study

Misplaced personal belongings are a recurring problem in educational institutions where students, faculty, and staff move continuously across classrooms, libraries, laboratories, and common areas. Items such as mobile phones, earphones, identification cards, calculators, keys, wallets, and bags are frequently left behind and later turned over to informal channels or office-based lost-and-found units. In many campuses, recovery still depends on handwritten logs, verbal descriptions, and chance follow-up. Under those conditions, documentation becomes inconsistent, ownership is difficult to verify, and retrieval is delayed (Mullins & Lee, 2017). This study is concerned with that practical difficulty: how an institution can compare lost and found submissions more reliably when evidence is visual, textual, or both.

The setting of the inquiry is institutional lost-and-found practice in a university environment, specifically within the operational context of AMA University. Coverage includes ticket-based reporting of lost and found items through a web platform, automated comparison of submissions, ranked presentation of candidate matches, and confirmation-centered claim coordination for desk pickup. The study does not investigate live camera surveillance or physical tracking devices; instead, it focuses on user-submitted photographs and descriptions as the primary evidence used in matching. Within that scope, the researcher examines how image embedding generation and semantic similarity analysis can support day-to-day recovery work that is currently performed largely by hand.

Several conditions make the problem urgent and researchable. First, informal recovery channels such as group chats and social media posts are widely used yet poorly searchable and weakly verified (Tan & Chong, 2023). Second, manual office logs remain vulnerable to disorganization, privacy exposure, and slow validation (Castro et al., 2022). Third, existing digital portals improve intake and browsing but often retain keyword search or staff-mediated pairing, which fails when wording differs or when a photograph carries most of the identity signal (Kim et al., 2019; Gupta & Sharma, 2020). Advances in contrastive vision–language models, particularly CLIP with Vision Transformer encoders, provide a theoretical and technical means to represent images and text in one embedding space and to score similarity objectively (Radford et al., 2021; Peng, 2025). These conditions justify a design-project inquiry into an AI-powered matching algorithm for campus lost-and-found tickets.

Accordingly, this study develops **FindIt**, a web-based matching system that encodes lost and found submissions with CLIP ViT-B/32, ranks candidate pairs through multimodal semantic similarity, and requires human confirmation before a claim is finalized and coordination emails are sent. The remainder of Chapter 1 presents the statement of the problem, objectives, significance, scope and limitations, hypotheses, theoretical and conceptual frameworks, and definition of terms. Related literature is reviewed in Chapter 2, while technical requirements and architecture are presented in Chapter 3. The expected contribution is a working matching pipeline and workflow that can improve the speed and structure of institutional item recovery while keeping final acceptance under user control.

## 1.2 Statement of the Problem

Institutional lost-and-found units lack an automated, multimodal method for comparing lost reports with found inventory when submissions contain images, text, or both. Manual comparison and keyword-based search are slow, inconsistent, and difficult to scale as ticket volume increases, which reduces the likelihood of timely and correct recovery.

In general terms, the study seeks to develop an AI-powered lost-and-found matching algorithm using image embedding generation and semantic similarity analysis for institutional item retrieval.

Specifically, the study seeks to answer the following questions:

1. What ticket-based reporting process can capture lost and found submissions—including images, descriptions, categories, locations, dates, and contact information—for centralized matching?

2. How can visual and textual features of lost and found submissions be represented as embeddings so that cross-modal comparison becomes possible?

3. How can embedding similarity be computed, fused, filtered, and ranked so that candidate matches are presented as an ordered shortlist with interpretable confidence levels?

4. How can ranked matching results be connected to a confirmation and notification workflow that supports coordinated pickup without silently linking incorrect items?

## 1.3 Objectives of the Study

### 1.3.1 General Objective

To develop an AI-powered lost-and-found matching algorithm that leverages image embedding generation and semantic similarity analysis to automate and improve the accuracy of item retrieval in institutional lost-and-found systems.

### 1.3.2 Specific Objectives

1. To design and implement a ticket-based web reporting system that accepts lost and found submissions with image and/or text inputs, category, location, date, and contact email, and stores those tickets for retrieval.

2. To generate normalized 512-dimensional image and text embeddings for each submission using CLIP ViT-B/32 and persist the vectors in PostgreSQL with pgvector for similarity search.

3. To implement a semantic similarity matching pipeline that computes multimodal cosine scores, applies adaptive fusion and contextual adjustments, assigns confidence tiers, and returns a ranked candidate shortlist for user review.

4. To integrate bidirectional matching (lost-to-found and found-to-lost) with a confirmation-centered claim workflow and email notifications that coordinate desk pickup after a match is accepted.

The objectives are intended to be specific, measurable through functional demonstration and ranking metrics, achievable within the prototype stack, relevant to campus recovery operations, and completable within the design-project timeline.

## 1.4 Significance of the Study

The study is significant because lost-and-found matching is a common campus service problem with direct effects on students, staff, and administrative workload. By demonstrating a working multimodal matcher, the research shows both the prevalence of the recovery gap and a practical response grounded in current vision–language technology.

**Students, faculty, and staff.** The system provides a single channel for filing reports and reviewing ranked candidates, reducing dependence on repeated office visits and scattered social posts.

**Campus lost-and-found offices.** Automated ranking lessens exhaustive manual comparison and organizes tickets into a confirmable workflow, allowing staff to focus on custody and final handoff.

**University management and innovation units.** The project illustrates applied digital transformation in a routine student service and documents an architecture that can be piloted institutionally.

**Future researchers and developers.** The study contributes an applied reference for CLIP-based multimodal fusion, thresholded ranking, and confirmation-centered claims in service information systems.

## 1.5 Scope and Limitation of the Study

### 1.5.1 Scope of the Study

The study covers the design and development of FindIt as an institutional lost-and-found matching prototype. In terms of locality and users, the system is intended for campus stakeholders—students, faculty, and staff—who can access a web interface over an internet connection. In terms of technical focus, the investigation centers on ticket intake, CLIP ViT-B/32 embedding generation, multimodal semantic similarity ranking, ranked shortlist presentation, claim confirmation, and claim-related email coordination for pickup through the campus lost-and-found desk. Evaluation within the design project emphasizes functional behavior of these components and ranking quality under controlled test conditions.

### 1.5.2 Limitations of the Study

The following constraints are recognized:

1. **Image and description quality.** Matching accuracy depends on lighting, angle, resolution, occlusion, and the completeness of user text. These factors exist because submissions are user-generated rather than studio-controlled; similar constraints appear in other real-world retrieval deployments.

2. **Pretrained encoder limits.** The prototype uses pretrained CLIP ViT-B/32. Without campus-specific fine-tuning, performance is bounded by the encoder’s prior training distribution and by look-alike items.

3. **Imperfect ranking.** Even with thresholds and shortlists, incorrect candidates may appear. Human confirmation is therefore required; automatic top-1 linking is not treated as final truth.

4. **Notification environment.** Prototype email may be written to a local outbox when institutional SMTP is unavailable. This affects demonstration of inbox delivery, not the matching logic itself.

5. **Institutional boundary.** Legal ownership disputes, physical storage policy, and custody decisions remain outside the algorithm and under campus procedure.

These limitations may temper absolute accuracy claims but also identify directions for later fine-tuning, larger labeled campus datasets, and production mail integration.

## 1.6 Hypotheses

Given the measurable nature of retrieval ranking, the study advances the following working hypotheses:

**H1.** Multimodal CLIP-based similarity ranking can place the correct corresponding item among the top-ranked candidates more effectively than unstructured manual browsing of the same ticket set.

**H2.** Applying confidence thresholds and ranked shortlist presentation improves usable recovery support by retaining correct lower-rank matches that would be missed under a strict top-1-only decision rule.

**H3.** A confirmation-centered claim workflow reduces the risk of incorrect automatic closure compared with linking tickets solely on a raw similarity score.

These hypotheses guide evaluation design in later chapters through ranking metrics such as hit rate at small *k*, mean reciprocal rank, and functional verification of claim confirmation behavior.

## 1.7 Theoretical Framework

The study is guided by contrastive vision–language representation learning, principally the CLIP framework (Radford et al., 2021). CLIP trains an image encoder and a text encoder so that matched image–text pairs are close in a shared embedding space while unmatched pairs are pushed apart. At inference time, cosine similarity between normalized embeddings becomes a principled score of semantic relatedness across modalities. The Vision Transformer (ViT-B/32) image tower used in this study is consistent with that theoretical line: visual inputs are mapped into the same comparable space as textual inputs.

Complementing CLIP is the information-retrieval view of ranked retrieval, in which systems return an ordered list of candidates rather than a single irreversible decision under ambiguity (Muennighoff et al., 2022). Early-rank metrics and human-in-the-loop confirmation follow naturally from that theory when queries are short, noisy, or partially observed—as is typical in lost-and-found tickets.

Together, these theories provide the blueprint for FindIt: embeddings as the representation mechanism, cosine similarity as the comparison mechanism, ranking and thresholds as the decision policy, and user confirmation as the safeguard before operational closure.

## 1.8 Conceptual Framework

The conceptual framework translates the theoretical blueprint into the specific variables and process of this study. FindIt is modeled as an Input–Process–Output system for multimodal matching and claim coordination.

**Input constructs**
- User and contact data (email, optional authenticated account)
- Lost ticket data (description, optional image, category, location, date)
- Found ticket data (image, optional description, category, location, date)
- Claim actions (selection of a ranked pair; confirmation or cancellation)

**Process constructs**
- Embedding generation through CLIP ViT-B/32 (image and text vectors)
- Multimodal cosine scoring (text–image and image–image signals when available)
- Adaptive score fusion with category, location, and date adjustments
- Confidence tiering, filtering, and ranked shortlist trimming
- Bidirectional matching triggers on lost and found submission
- Claim state management and email notification

**Output constructs**
- Persisted tickets and embeddings
- Ranked candidate shortlists with scores and tiers
- Claim records
- Coordination emails for confirmed claim events
- Operational queue visibility

**Presumed relationships.** Richer multimodal evidence and higher fused similarity increase the probability that the correct item appears early in the shortlist. Thresholding reduces noise. Confirmation converts a ranked suggestion into an accepted operational link. Weak evidence, generic appearance, or vague text weaken ranking quality and increase dependence on user judgment.

This conceptual model is the researcher’s map of how the research problem is explored in the FindIt prototype and how later evaluation should relate inputs, matching processes, and recovery outputs.

## 1.9 Definition of Terms

The following terms are defined as used in this study. Where useful, both constitutive and operational meanings are provided.

**FindIt** — Constitutive: the AI-powered campus lost-and-found matching platform developed in this study. Operational: the web client, FastAPI services, PostgreSQL/pgvector store, CLIP matching pipeline, and claim/email workflow implemented in the prototype.

**CLIP (Contrastive Language–Image Pre-training)** — Constitutive: a vision–language model that learns a joint embedding space for images and text. Operational: the OpenAI CLIP ViT-B/32 checkpoint loaded for encoding in FindIt.

**Image Embedding / Text Embedding** — Constitutive: numeric vector representations of a photograph or description. Operational: 512-dimensional L2-normalized vectors produced by CLIP’s image or text encoder.

**Semantic Similarity Analysis** — Constitutive: estimation of how closely two submissions refer to the same item. Operational: cosine similarity on normalized embeddings, including fused multimodal scores in the ranking pipeline.

**Multimodal Matching** — Constitutive: comparison that uses more than one modality-derived signal. Operational: combination of available CLIP similarities such as lost text↔found image, lost image↔found image, and found text↔lost image.

**Confidence Tier** — Constitutive: categorical interpretation of match strength. Operational: labels assigned from final score bands used in FindIt (`strong`, `possible`, `weak`), with scores below the weak threshold excluded.

**Ranked Candidate List** — Constitutive: ordered set of potential matches for user review. Operational: thresholded, trimmed shortlist returned by the matching service, from which a non-top result may still be selected.

**Ticket-Based Reporting** — Constitutive: structured submission of lost or found records. Operational: `POST /lost` and `POST /found` flows with required and optional fields persisted as database rows.

**Claim Confirmation** — Constitutive: acceptance that links a lost report to a found report. Operational: claim creation and confirmation actions that update statuses and trigger coordination emails.

**Matching Accuracy** — Constitutive: correctness of retrieval. Operational: evaluation measures such as hit rate at rank *k* and mean reciprocal rank on labeled test pairs.

---

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

# CHAPTER 3
# TECHNICAL REQUIREMENTS

This chapter presents the technical requirements for the FindIt system. It covers the hardware, software, and peopleware required to develop, deploy, and maintain the platform so that FindIt can function as an AI-powered lost-and-found matching and claim-coordination service.

## 3.1 System Requirements

### 3.1.1 Hardware

**Table 1. End-User Device Hardware Requirements**

| Component | Specification |
|---|---|
| Client device | Desktop, laptop, tablet, or smartphone capable of running a modern web browser |
| Display | Resolution suitable for forms, image review, and ranked results; responsive layout supported |
| Camera / media | Device camera or photo library access for item uploads; clear, well-lit images recommended |
| Memory and storage | Sufficient free space for browser operation and temporary media selection |
| Connectivity | Stable Wi-Fi or mobile data for API communication and image upload |

**Table 2. Desktop / Workstation Hardware Requirements**

| Component | Specification |
|---|---|
| Desktop workstation | Computer used for development, demonstration, or administrative review |
| Processor and memory | Multi-core CPU; minimum 8 GB RAM, 16 GB recommended when API, database, and CLIP run locally |
| Storage | Adequate disk for project files, database data, uploaded images, and mail outbox artifacts |
| Display and connectivity | Monitor suitable for dashboard and form review; wired or wireless network access to services |
| Operating system and browser | Windows 10+, macOS 12+, or equivalent Linux desktop with current Chrome, Firefox, or Edge |

**Table 3. Server Host Hardware Requirements**

| Component | Specification |
|---|---|
| Application host | Machine or virtual host running the FindIt API and related services |
| Processor | Multi-core CPU to support request handling and CLIP inference |
| Graphics (optional) | CUDA-capable GPU to accelerate embedding generation; CPU mode supported |
| Memory | At least 8 GB RAM for prototype stacks; additional memory preferred under concurrent use |
| Storage and network | Disk for PostgreSQL, uploads, and model cache; network ports for frontend, API, and database |

### 3.1.2 Software

**Table 4. Frontend Application Technology Stack**

| Component | Specification |
|---|---|
| Web client | Static FindIt interface implemented with HTML, CSS, and JavaScript |
| Delivery | Served by nginx in the Docker Compose development environment |
| Browser support | Current Google Chrome, Mozilla Firefox, Microsoft Edge, or Safari |
| Core functions | Registration and sign-in, lost and found reporting, ranked match review, claim confirmation, and queue inspection |

**Table 5. Backend / API Software Requirements**

| Component | Specification |
|---|---|
| Python | Primary language for backend services, AI integration, and data access |
| FastAPI | High-performance framework for RESTful endpoints among client, matching logic, and database |
| PostgreSQL 16 | Relational store for users, lost items, found items, and claims |
| pgvector | Extension for storing and distance-ordering 512-dimensional embeddings |
| JWT | Stateless authentication for registered sessions |
| Alembic | Database schema migration and versioning |

**Table 6. AI and Matching System Software Requirements**

| Component | Specification |
|---|---|
| PyTorch | Deep learning runtime for model inference |
| CLIP ViT-B/32 | Vision–language model producing aligned image and text embeddings |
| Embedding format | 512-dimensional L2-normalized vectors |
| Similarity | Cosine similarity via normalized vector dot product |
| Ranking policy | Adaptive multimodal fusion; category multiplier; location and date boosts; confidence tiers; ranked shortlist trimming |
| Category assistance | CLIP similarity against predefined category text prompts |

**Table 7. Notification and Deployment Software Requirements**

| Component | Specification |
|---|---|
| Email service | SMTP delivery when configured; filesystem mail outbox for prototype demonstration |
| Notification events | Claim acceptance, cancellation, and processed coordination messages |
| Docker Compose | Containerized local deployment of API, PostgreSQL/pgvector, and frontend services |

### 3.1.3 Peopleware

**Table 8. Development Team Requirements**

| Role | Responsibility |
|---|---|
| Frontend developer | Implements the web interface for reporting, match review, authentication, and claims |
| Backend developer | Develops FastAPI routes, persistence, authentication, and claim workflow logic |
| AI / matching implementer | Integrates CLIP encoding, similarity scoring, ranking thresholds, and evaluation utilities |
| Database administrator | Configures PostgreSQL with pgvector and maintains migrations and data integrity |
| Quality assurance tester | Verifies reporting, ranking behavior, claim confirmation, and notification outputs |

**Table 9. Support and Maintenance Team Requirements**

| Role | Responsibility |
|---|---|
| System administrator | Deploys and monitors services, storage, and network configuration |
| Security specialist | Reviews authentication, access control, and protection of contacts and uploads |
| Campus desk personnel | Handles physical custody and release after digital match confirmation |
| Quality assurance / tester | Re-tests releases for functionality, reliability, and usability before demonstration or pilot use |

## 3.2 System Architecture

The FindIt system adopts a layered architecture that supports reporting, multimodal matching, and claim coordination within the institution.

The presentation layer provides the browser-based interface for submitting tickets, reviewing ranked candidates, confirming claims, and managing account access. Administrative views support inspection of queue and claim activity.

The application layer exposes RESTful services for authentication, category prediction, lost and found submission, match responses, and claim lifecycle operations. Business rules enforce required fields, exclude self-matches by contact email, and manage status transitions for items and claims.

The AI matching layer loads CLIP ViT-B/32 to encode images and text, computes multimodal cosine similarities, fuses available signals, assigns confidence tiers, and returns a trimmed ranked list. Embedding vectors are persisted for reuse, and pgvector distance ordering may assist candidate organization when image embeddings are present.

The data layer stores users, reports, claims, and embeddings in PostgreSQL, while uploaded images are retained on the application host for review during matching and claims.

The notification layer generates email messages for claim workflow events. Depending on configuration, messages are transmitted through SMTP or written to a local outbox for verifiable prototype demonstration.

By separating interface, matching computation, persistence, and notification concerns, FindIt maintains a coherent end-to-end path: ticket submission, embedding generation, ranked semantic matching, user confirmation, and email-supported pickup coordination at the campus lost-and-found desk.
