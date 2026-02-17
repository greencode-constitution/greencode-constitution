# Run llama.cpp benchmark with inlined prompt

PROMPT="The development of artificial intelligence has been one of the most transformative technological advances of the modern era. From its theoretical foundations in the mid-20th century to today's sophisticated neural networks and large language models, AI has evolved from a niche academic pursuit into a technology that permeates nearly every aspect of contemporary life.

The emergence of machine learning in the 1980s and 1990s marked a paradigm shift in AI research. Instead of manually programming rules, researchers began developing algorithms that could learn patterns from data. Neural networks, inspired by the structure of biological brains, gained renewed interest after decades of relative obscurity. The development of backpropagation and other training algorithms made it possible to train multi-layer networks, opening new possibilities for pattern recognition and classification tasks.

The 21st century has witnessed an explosion of progress in artificial intelligence, driven largely by three key factors: the availability of massive datasets, exponential increases in computational power, and algorithmic innovations in deep learning. Modern neural networks with millions or even billions of parameters can now perform tasks that were once thought to require human-level intelligence, from recognizing objects in images to translating between languages and engaging in natural conversation.

Large language models represent one of the most remarkable achievements in recent AI research. These models, trained on vast corpora of text data, have demonstrated surprising capabilities in understanding context, generating coherent text, and even reasoning about complex problems. They have found applications in diverse fields, from customer service and content creation to scientific research and software development.

However, the rapid advancement of AI also raises important questions about safety, ethics, and societal impact. Concerns about bias in AI systems, the potential for misuse, job displacement, and the long-term implications of increasingly capable AI systems have sparked intense debate among researchers, policymakers, and the public. As AI continues to evolve, addressing these challenges while fostering beneficial innovation remains a critical priority for the field.

What are the most important considerations when developing AI systems to ensure they benefit society while minimizing potential risks?"

echo "==> Running llama.cpp benchmark..."
./build/bin/llama-bench -m models/Qwen3-8B-Q4_K_M.gguf -p 1000 -n 2500 -r 1 2>&1 | awk '
/pp[0-9]+/ {
    match($0, /pp([0-9]+)/, arr);
    prompt_tokens=arr[1];
    match($0, /([0-9]+\.[0-9]+) ±/, speed);
    prompt_speed=speed[1]
}
/tg[0-9]+/ {
    match($0, /tg([0-9]+)/, arr);
    gen_tokens=arr[1];
    match($0, /([0-9]+\.[0-9]+) ±/, speed);
    gen_speed=speed[1]
}
END {
    print "Input:  " prompt_tokens " tokens @ " prompt_speed " t/s"
    print "Output: " gen_tokens " tokens @ " gen_speed " t/s"
}'
