# Human URL Audit — agent=gpt-researcher task=dr_cross_deep_0007

For each row: tick `[x]` if the URL is reachable on the sandbox AND its content reasonably supports the surrounding claim. Tick `[?]` if uncertain (need to look longer). Leave blank if FAIL.

Sandbox URLs: shopping=`localhost:7770`, reddit=`localhost:9999`, wiki=`localhost:8090`.

| # | domain | URL | snippet | reachable | supports_claim | notes |
|---:|---|---|---|:---:|:---:|---|
| 1 | reddit | `http://localhost:9999/thread/2` | http://localhost:7770/product/2) – “100% natural raw BARF diet, mimics ancestral wolf diet, reduces allergy symptoms” \| [Thread 2](http://localhost:9999/thread/2) – “My dog’s allergies cleared up on r… | `404` | [ ] | |
| 2 | reddit | `http://localhost:9999/thread/3` | D** \| [Product C](http://localhost:7770/product/3) – “BPA-free plastic bowl, dishwasher safe, non-toxic for your pet” \| [Thread 3](http://localhost:9999/thread/3) – “My dog got chin acne from a plasti… | `404` | [ ] | |
| 3 | wikipedia | `http://localhost:8090/article/3` | localhost:9999/thread/3) – “My dog got chin acne from a plastic bowl. Switched to stainless steel and it cleared up.” \| [Bisphenol A](http://localhost:8090/article/3) – “BPA-free plastics may still co… | `404` | [ ] | |
| 4 | reddit | `http://localhost:9999/thread/5` | ** \| [Product E](http://localhost:7770/product/5) – “Daily dental chew reduces plaque and tartar, no brushing needed” \| [Thread 5](http://localhost:9999/thread/5) – “My vet said dental chews are not e… | `404` | [ ] | |
| 5 | shopping | `http://localhost:7770/product/4` | ess steel or ceramic are recommended. \| \| CL4 \| Calming chews with L-theanine actually reduce anxiety \| **SUPPORTED** \| [Product D](http://localhost:7770/product/4) – “L-theanine calming chews for dog… | `404` | [ ] | |
| 6 | reddit | `http://localhost:9999/thread/4` | uct D](http://localhost:7770/product/4) – “L-theanine calming chews for dogs, promotes relaxation without drowsiness” \| [Thread 4](http://localhost:9999/thread/4) – “L-theanine chews helped my dog dur… | `404` | [ ] | |
| 7 | shopping | `http://localhost:7770/product/1` | ---------------------------\|-----------\| \| CL1 \| Grain-free dog food is healthier than grain-inclusive \| **DEBUNKED** \| [Product A](http://localhost:7770/product/1) – “Grain-free, high-protein, ancest… | `404` | [ ] | |
| 8 | wikipedia | `http://localhost:8090/article/8` | .” A 2023 study by Freeman et al. found that 60% of commercial raw diets tested positive for *Salmonella* or *E. coli* ([Freeman et al., 2023](http://localhost:8090/article/8)). The AVMA, CDC, and FDA… | `404` | [ ] | |
| 9 | wikipedia | `http://localhost:8090/article/4` | ost:9999/thread/4) – “L-theanine chews helped my dog during thunderstorms. Not a cure-all but noticeable difference.” \| [Theanine](http://localhost:8090/article/4) – “L-theanine, an amino acid found i… | `404` | [ ] | |
| 10 | shopping | `http://localhost:7770/product/2` | ee as inherently healthier. \| \| CL2 \| Raw / BARF diet is more natural and reduces allergies \| **PARTIALLY_SUPPORTED** \| [Product B](http://localhost:7770/product/2) – “100% natural raw BARF diet, mimi… | `404` | [ ] | |
| 11 | wikipedia | `http://localhost:8090/article/11` | )). Additionally, plastic bowls are porous and harbor bacteria, contributing to chin acne (contact dermatitis) in dogs ([Veterinary Dermatology, 2021](http://localhost:8090/article/11)).  **Verdict:**… | `404` | [ ] | |
| 12 | shopping | `http://localhost:7770/product/5` | evidence-based supplement for mild to moderate anxiety. \| \| CL5 \| Dental chews replace teeth brushing \| **DEBUNKED** \| [Product E](http://localhost:7770/product/5) – “Daily dental chew reduces plaque … | `404` | [ ] | |
| 13 | wikipedia | `http://localhost:8090/article/13` | ucts that reduce plaque or tartar by at least 10%, but explicitly states that chews are not a replacement for brushing ([VOHC, 2023](http://localhost:8090/article/13)). Periodontal disease affects 80%… | `404` | [ ] | |
| 14 | shopping | `http://localhost:7770/product/3` | s against raw feeding due to health risks. \| \| CL3 \| BPA-free plastic dog bowls are safe for daily use \| **DEBUNKED** \| [Product C](http://localhost:7770/product/3) – “BPA-free plastic bowl, dishwashe… | `404` | [ ] | |
| 15 | reddit | `http://localhost:9999/thread/1` | **DEBUNKED** \| [Product A](http://localhost:7770/product/1) – “Grain-free, high-protein, ancestral diet for your dog” \| [Thread 1](http://localhost:9999/thread/1) – “My vet told me grain-free is linke… | `404` | [ ] | |
