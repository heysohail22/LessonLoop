# Introduction to RAG

## What is RAG?

RAG stands for Retrieval-Augmented Generation. It is a method that pairs a generative model with retrieval (R1). A generative model is an artificial intelligence program that can write text or answers. Retrieval means searching and finding relevant information from external files or documents. In RAG, relevant information is supplied to the AI as context for an answer (R1). Context is the background information supplied along with a question to help the AI understand what to look at.

## Why it matters

An AI model learns from a vast amount of data, but it does not know private, new, or specific documents unless you show them. RAG uses external knowledge without requiring retraining for each document update (R3). Retraining means teaching the AI model from scratch or updating its core internal memory using heavy computer processing. Because of RAG, when documents change or new rules are added, you do not need to retrain the whole model. Instead, updated documents just need to be prepared or synced before they are searchable (R2). Note that document updates are not guaranteed to be instant (R2).

## How it works

RAG works in three main steps. First, preparation: documents are split into smaller passages and indexed for retrieval (R2). An index is like an organized book index or a digital list that helps the system quickly find where specific topics are located. Second, retrieval: when a user asks a question, the system searches the index and finds the most relevant passages. Third, generation: the generative model takes the question and the retrieved passages as context to write a clear, helpful answer.

## A worked example

This is a fictional example. Question: What is the library fee for students at Oakwood College? Source passage from the college rulebook: Library books can be borrowed for fourteen days. Students must pay a late fee of ten rupees per day if a book is returned after the due date. Supported answer: Based on the rulebook, students at Oakwood College must pay a late fee of ten rupees per day if a library book is returned after the due date.

## What can go wrong?

RAG can improve answers, but it does not guarantee correctness; source quality and retrieval matter (R3). Sometimes, the retrieval step fails to find the right passage, or it misses relevant material. Even when the source material is completely accurate, the model can still generate wrong information (R3). This means you should always check important facts yourself.

## Try it yourself

True or False: RAG requires retraining the AI model every single time a document is updated, and it guarantees that generated answers will always be completely correct.

## Answer explained

False. RAG uses external knowledge without requiring retraining for each document update (R3). Also, RAG does not guarantee correctness; source quality and retrieval matter, and the model can generate wrong information even with accurate source material (R3).

## Reference notes

**R1:** https://csrc.nist.gov/glossary/term/retrieval_augmented_generation — RAG pairs a generative model with retrieval; relevant information is supplied as context for an answer.

**R2:** https://docs.aws.amazon.com/bedrock/latest/userguide/kb-how-it-works.html — A common preparation method splits documents into passages and indexes them for retrieval. Retrieved passages help answer a question. Updated documents must be prepared or synced before they are searchable; updates are not guaranteed to be instant (https://docs.aws.amazon.com/bedrock/latest/userguide/kb-data-source-sync-ingest.html).

**R3:** https://aws.amazon.com/what-is/retrieval-augmented-generation/ — RAG uses external knowledge without requiring retraining for each document update. It can improve answers but does not guarantee correctness; source quality and retrieval matter. The model can generate wrong information even with accurate source material (https://aws.amazon.com/blogs/machine-learning/reducing-hallucinations-in-llm-agents-with-a-verified-semantic-cache-using-amazon-bedrock-knowledge-bases/).
