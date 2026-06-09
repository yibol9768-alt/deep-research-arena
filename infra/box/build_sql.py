import json, sys
threads = json.load(open("/opt/deep_reserch/.dra_tmp/coffee_threads.json"))
USERS = [13915, 35361]  # MarvelsGrantMan136, Don_Gato1

def esc(s):
    return s.replace("'", "''")

lines = []
lines.append("BEGIN;")
# Create coffee forum if absent, id = max+1
lines.append("""
DO $$
DECLARE fid bigint;
BEGIN
  SELECT id INTO fid FROM forums WHERE normalized_name='coffee';
  IF fid IS NULL THEN
    SELECT COALESCE(max(id),10000)+1 INTO fid FROM forums;
    INSERT INTO forums (id, name, title, sidebar, created, normalized_name, featured, description, background_image_mode, moderation_log_public)
    VALUES (fid, 'coffee', 'Home Coffee Brewing', 'Discuss home coffee brewing: pour-over, espresso, French press, grinders, beans.', now(), 'coffee', false, 'Home coffee brewing community.', 'tile', true);
    RAISE NOTICE 'created coffee forum id=%', fid;
  ELSE
    RAISE NOTICE 'coffee forum exists id=%', fid;
  END IF;
END $$;
""")
# Insert submissions
for i, t in enumerate(threads):
    uid = USERS[i % len(USERS)]
    title = esc(t["title"])
    body = esc(t["body"])
    flag = "dra_coffee_%02d" % i
    lines.append(f"""
INSERT INTO submissions
  (id, forum_id, user_id, title, "timestamp", url, body, sticky, ranking, moderated, user_flag, locked, last_active, comment_count, net_score, visibility, media_type)
SELECT
  (SELECT COALESCE(max(id),137402)+1 FROM submissions),
  (SELECT id FROM forums WHERE normalized_name='coffee'),
  {uid},
  '{title}',
  now() - interval '{i} hours',
  NULL,
  '{body}',
  false,
  (SELECT COALESCE(max(id),137402)+1 FROM submissions),
  false,
  '{flag}',
  false,
  now() - interval '{i} hours',
  0,
  {3 + (i % 9)},
  'visible',
  'url';
""")
lines.append("COMMIT;")
open("/opt/deep_reserch/.dra_tmp/seed_coffee.sql","w").write("\n".join(lines))
print("wrote SQL with", len(threads), "inserts")
