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
