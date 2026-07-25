PM Triage documentation, in essay form.

This folder holds listen-friendly versions of every markdown document in docs. The content is the same; the shape is different. Tables have been turned into sentences, metric grids into spoken comparisons, and reference lists into paragraphs, so that a text-to-speech reader can carry you through a document from start to finish without you needing to look at the screen to know what a row or a column meant.

Nothing here replaces the originals. Each file in this folder corresponds to the file of the same name one directory up, and the originals remain the canonical, scannable versions for reading with your eyes.

What is in here, and the order to listen in.

The natural starting point is the FDE defense master guide, which maps the project onto the company rubric, lays out the seven-minute presentation, and states the exact claims, counts, and contingencies. It is the first document to learn, and everything else is either a deeper cut of it or a specialist follow-up to it.

After that comes the code and data-flow reference, which walks every API endpoint, every critical backend and frontend function, every database table, every state transition, every test group, and two worked end-to-end examples. It is meant to be listened to alongside the source code rather than on its own.

Third is the production challenge question-and-answer document, a collection of adversarial questions about scale, security, failure modes, artificial intelligence risk, integration, customer delivery, and the honest gaps that remain before this would be a production system. The intended use is to answer each one aloud before hearing the written answer.

The remaining documents are specialist references you reach for when a particular question comes up. The architecture essay gives the one-glance picture, the account of who decides what, the runtime drill-down, and the reasoning behind each boundary. The architecture and interview guide covers the complete backend path, the database schemas, the mappings, the tool calls, and definitions of the technologies involved. The current status essay separates what is complete from what is partial and what is still pending. The evaluation guide explains every measured number in plain language. The cost control essay covers model choice, the lifecycle of a paid call, and the spending caps. The machine learning experiment essay describes the broad model that was rejected, the narrow model that replaced it in production, the grouped data splits, the saved artifact, and the honest limits of the whole exercise. The defense pack is a condensed set of presentation and interview answers. The economics essay gives provenance for the illustrative downtime-cost inputs. And the decision context essay is a short note on current architecture decisions and their limitations.

Two files in the original folder are not documents in this sense and have no essay version. The presentation is a self-contained HTML deck of five slides covering the system, both architecture views, every measured evaluation number, and the rubric the artifact is judged against; you open it in a browser, move with the arrow keys, and print it to PDF for five landscape pages. GitHub will not render it inline. The second is an archived HTML export of the defense pack from before the nineteenth of July 2026, retained for history only. It contains stale evaluation and model numbers and should not be presented.

The root README of the repository, one level further up, is the installation and product overview rather than part of this documentation set.

The recommended preparation sequence.

Listen to the FDE defense master guide first. Then rehearse the application itself without notes. Then go through the code and data-flow reference with the source open beside you. Then answer the production challenge questions out loud, before listening to the answers. Finally, keep the evaluation, machine learning, cost, architecture, and economics essays in reserve for specialist follow-up questions.
