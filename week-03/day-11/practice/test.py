# from langchain_text_splitters import RecursiveCharacterTextSplitter

# page1 = "The quick brown fox jumps over the lazy dog near the old oak tree by the river bank."
# page2 = "Meanwhile in a distant town a baker prepared fresh bread each morning before the sun rose."

# splitter = RecursiveCharacterTextSplitter(chunk_size=50, chunk_overlap=10)

# # Approach A: Saturday's style - glue pages together FIRST, then chunk
# combined_text = page1 + " " + page2
# chunks_combined = splitter.split_text(combined_text)

# print("=== Saturday: whole doc chunked as one continuous string ===")
# for i, chunk in enumerate(chunks_combined):
#     print(f"Chunk {i}: {chunk!r}")

# # Approach B: Today's style - chunk EACH page separately, then combine the results
# chunks_page1 = splitter.split_text(page1)
# chunks_page2 = splitter.split_text(page2)
# chunks_separate = chunks_page1 + chunks_page2

# print("\n=== Today: each page chunked independently ===")
# for i, chunk in enumerate(chunks_separate):
#     print(f"Chunk {i}: {chunk!r}")