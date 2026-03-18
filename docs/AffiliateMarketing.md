# Affiliate Marketing

This class is responsible for the Affiliate Marketing part of 24DinMaiPaisaDouble. It uses Ollama (as all other classes) as its way to utilize the power of LLMs, in this case, to generate tweets, based on information about an **Amazon Product**. 24DinMaiPaisaDouble will scrape the page of the product, and save the **product title**, and **product features**, thus having enough information to be able to create a pitch for the product, and post it on Twitter.

## Relevant Configuration

- `ollama_model`: The model that will be used to generate the pitch.
- `twitter_language`: The language that will be used to generate & post the tweet.
- `gemini_image_api_key`: The API key that will be used to generate the images (fallback).
