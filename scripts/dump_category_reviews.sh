#!/usr/bin/env bash
# Box-side dump for the review-sentiment deriver (EXECUTION_PLAN P3.2, #27a).
# Usage: dump_category_reviews.sh "60,222,210,242" /tmp/reviews_cat.tsv
# Emits TSV: product_id, url_key, product_name, price, rating_summary(0-100),
#            reviews_count, review_rating(1-5 votes avg per review), review_title, review_detail
# One row per review for every product in the given categories, plus the
# product description as a separate file <out>.desc.tsv for the numeric-spec
# contradiction extractor (#27b).
set -euo pipefail
CATS="${1:?category ids csv}"
OUT="${2:?output tsv}"

docker exec -i dr_sandbox_shopping mysql -u magentouser -pMyPassword -s -N magentodb <<SQL > "$OUT"
SELECT p.entity_id,
       uk.value,
       REPLACE(REPLACE(nm.value,'\t',' '),'\n',' '),
       IFNULL(pr.value,''),
       IFNULL(res.rating_summary,''),
       IFNULL(res.reviews_count,0),
       IFNULL((SELECT AVG(rov.value)*20 FROM rating_option_vote rov
               WHERE rov.review_id = r.review_id), ''),
       REPLACE(REPLACE(IFNULL(rd.title,''),'\t',' '),'\n',' '),
       REPLACE(REPLACE(IFNULL(rd.detail,''),'\t',' '),'\n',' ')
FROM catalog_category_product cp
JOIN catalog_product_entity p ON p.entity_id = cp.product_id
JOIN catalog_product_entity_varchar uk ON uk.entity_id = p.entity_id
  AND uk.attribute_id = (SELECT attribute_id FROM eav_attribute
                         WHERE entity_type_id=4 AND attribute_code='url_key')
JOIN catalog_product_entity_varchar nm ON nm.entity_id = p.entity_id
  AND nm.attribute_id = (SELECT attribute_id FROM eav_attribute
                         WHERE entity_type_id=4 AND attribute_code='name')
LEFT JOIN catalog_product_entity_decimal pr ON pr.entity_id = p.entity_id
  AND pr.attribute_id = (SELECT attribute_id FROM eav_attribute
                         WHERE entity_type_id=4 AND attribute_code='price')
LEFT JOIN review_entity_summary res ON res.entity_pk_value = p.entity_id AND res.store_id = 1
LEFT JOIN review r ON r.entity_pk_value = p.entity_id
LEFT JOIN review_detail rd ON rd.review_id = r.review_id
WHERE cp.category_id IN ($CATS)
GROUP BY p.entity_id, r.review_id
SQL

docker exec -i dr_sandbox_shopping mysql -u magentouser -pMyPassword -s -N magentodb <<SQL > "${OUT}.desc.tsv"
SELECT DISTINCT p.entity_id,
       REPLACE(REPLACE(IFNULL(ds.value,''),'\t',' '),'\n',' ')
FROM catalog_category_product cp
JOIN catalog_product_entity p ON p.entity_id = cp.product_id
LEFT JOIN catalog_product_entity_text ds ON ds.entity_id = p.entity_id
  AND ds.attribute_id = (SELECT attribute_id FROM eav_attribute
                         WHERE entity_type_id=4 AND attribute_code='description')
WHERE cp.category_id IN ($CATS)
SQL

wc -l "$OUT" "${OUT}.desc.tsv"
