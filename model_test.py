from transformers import pipeline
classifier = pipeline("text-classification", model="tabularisai/multilingual-sentiment-analysis")
print(classifier("오늘 정말 기분이 좋아요"))