# DRA paper-method 336-Query candidate bank

## Release meaning

This directory contains source-probed Query candidates produced from public GeneratorViews.
It does **not** contain completed Evidence Graphs, independent human span approvals, hidden
answerability proofs, blind-review approvals, or formal-release certificates. Every row has
`formal_eligible=false` until those paper-required stages are completed.

## Relationship to the paper method

This bank implements the public-query candidate stage of the paper's old method:

1. Every angle has live discovery roots in frozen Magento, Postmill, and Kiwix.
2. Every candidate is compiled from a public `GeneratorView` containing only scenario,
   constraints, candidate actions, and target.
3. The bank is balanced across the paper's three structures: constraint match and select,
   mechanism-to-case application, and evidence reconciliation.
4. Deterministic checks enforce option/constraint preservation, natural length, multi-branch
   language, and the absence of URLs, evaluator vocabulary, and procedural source quotas.

The paper requires Evidence Records and a verified Evidence Graph before formal generation.
Because those human-verified assets do not yet exist for these new angles, these rows are
intake candidates for that pipeline, not claims of formal paper-compliant release. Each
candidate has one provisional structure; the verified graph must confirm or replace it.

## Inventory

- Topic packs: 28
- Independent scenarios/angles: 336
- Query candidates: 336
- Passed source probe and public hard rules: 336
- Requires revision: 0

### Task structures

- `constraint_match_and_select`: 112
- `mechanism_to_case_application`: 112
- `evidence_reconciliation`: 112

### Families

- `consumer_technology`: 48
- `creative_technology`: 12
- `finance_and_decisions`: 12
- `health_and_activity`: 24
- `home_and_food`: 36
- `home_and_work`: 48
- `lifestyle_and_travel`: 24
- `media_and_creativity`: 48
- `personal_care`: 24
- `science_and_technology`: 36
- `society_and_place`: 24

### Topic coverage

| Topic pack | Family | Twelve independent research angles | Queries |
|---|---|---|---:|
| Audio and headphones | `consumer_technology` | `long_flight_glasses`, `open_office_calls`, `children_shared_devices`, `balcony_camping_audio`, `apartment_tv_audio`, `vinyl_first_setup`, `solo_podcast_recording`, `workshop_hearing_protection`, `sleep_audio_shared_room`, `silent_instrument_practice`, `multiroom_rental_audio`, `outdoor_event_pa` | 12 |
| Mobile phones and accessories | `consumer_technology` | `family_charging`, `case_long_term`, `replace_old_phone`, `car_navigation`, `weekend_power_bank`, `screen_protection_tradeoff`, `bike_navigation_mount`, `family_photo_backup`, `water_activity_protection`, `durable_charge_cables`, `travel_connectivity`, `one_hand_accessibility` | 12 |
| Computers, input devices, and displays | `consumer_technology` | `shared_office_keyboard`, `mixed_work_monitor`, `family_backup`, `one_cable_desk`, `shared_desk_mouse`, `remote_teaching_camera`, `portable_laptop_posture`, `dual_monitor_mounting`, `power_outage_desktop`, `accurate_print_preview`, `memory_card_workflow`, `sunlit_secondary_display` | 12 |
| Gaming and consoles | `consumer_technology` | `family_console`, `controller_replacement`, `first_vr`, `train_handheld`, `shared_living_room_gaming`, `racing_game_controls`, `retro_game_display`, `accessible_one_hand_play`, `local_party_games`, `console_storage_expansion`, `quiet_night_gaming`, `travel_game_library` | 12 |
| Cameras, photography, and video | `creative_technology` | `indoor_sports_parent`, `travel_lenses`, `family_video`, `home_portraits`, `hiking_tripod`, `commuter_camera_bag`, `outdoor_video_sound`, `home_photo_printing`, `reliable_memory_cards`, `water_reflection_filter`, `small_object_macro`, `family_archive_digitizing` | 12 |
| Home office and ergonomics | `home_and_work` | `tall_remote_worker`, `sit_stand_decision`, `wrist_pain_input`, `paper_light_office`, `evening_desk_lighting`, `video_call_background`, `standing_desk_floor_support`, `echoing_call_room`, `secure_paper_disposal`, `desk_power_management`, `small_office_whiteboard`, `shared_room_privacy` | 12 |
| Kitchen, cookware, and food storage | `home_and_food` | `first_cookware`, `one_good_knife`, `weeknight_appliance`, `meal_prep_storage`, `cutting_board_system`, `soup_sauce_blending`, `roast_temperature_control`, `bread_baking_vessel`, `nonreactive_utensils`, `rental_water_filtration`, `small_kitchen_drying`, `extra_induction_burner` | 12 |
| Coffee, tea, and beverages | `home_and_food` | `beginner_brewing`, `grinder_upgrade`, `tea_and_coffee_kettle`, `bulk_bean_storage`, `repeatable_coffee_scale`, `reusable_filter_choice`, `commuter_travel_mug`, `brewing_water_quality`, `summer_cold_brew`, `milk_texture_at_home`, `loose_leaf_at_work`, `decaf_evening_routine` | 12 |
| Snacks, nutrition, and pantry choices | `home_and_food` | `work_snack_drawer`, `lower_sugar_sweets`, `plant_based_breakfast`, `storm_pantry`, `day_hike_snacks`, `school_allergen_aware`, `night_shift_vending`, `low_waste_snack_packing`, `vegetarian_travel_protein`, `family_movie_snacks`, `humid_climate_crunch`, `road_trip_drinks` | 12 |
| Fitness, training, and recovery | `health_and_activity` | `small_home_strength`, `run_tracking`, `soreness_tool`, `quiet_cardio`, `shared_yoga_floor`, `strength_training_footwear`, `summer_run_hydration`, `doorway_pull_training`, `early_morning_visibility`, `balance_training_home`, `travel_mobility_tools`, `jump_training_noise` | 12 |
| Outdoor, camping, and preparedness | `health_and_activity` | `weekend_shelter`, `drinking_water`, `night_lighting`, `off_grid_power`, `three_season_sleep_system`, `camp_cooking_fuel`, `overnight_pack_fit`, `trail_navigation_backup`, `wildlife_food_storage`, `mosquito_camp_protection`, `trekking_pole_choice`, `compact_camp_furniture` | 12 |
| Footwear and technical apparel | `lifestyle_and_travel` | `mixed_surface_running`, `salt_winter_commute`, `city_rain_layer`, `cold_base_layers`, `rocky_day_hikes`, `all_day_standing`, `warm_weather_water_shoes`, `winter_hand_layers`, `summer_sun_headwear`, `multi_day_hiking_socks`, `packable_insulation_layer`, `visible_cycle_clothing` | 12 |
| Bags, luggage, and travel accessories | `lifestyle_and_travel` | `frequent_carry_on`, `wet_bike_commute`, `small_suitcase_packing`, `international_power`, `underseat_personal_item`, `one_bag_toiletries`, `secure_day_sightseeing`, `packable_trip_daypack`, `formal_clothes_transport`, `luggage_weight_control`, `family_document_organization`, `rainproof_camera_daybag` | 12 |
| Beauty, skin care, and hair tools | `personal_care` | `daily_sunscreen`, `simple_skin_routine`, `drying_thick_hair`, `sensitive_hair_removal`, `low_waste_hair_washing`, `wet_hair_detangling`, `occasional_heat_styling`, `winter_lip_protection`, `frequent_hand_washing`, `basic_nail_maintenance`, `makeup_tool_hygiene`, `scalp_focused_drying` | 12 |
| Personal wellness and home health devices | `personal_care` | `oral_care_upgrade`, `day_sleep`, `dry_winter_allergy`, `home_vitals`, `gentle_morning_wake`, `hydration_tracking`, `weekly_pill_organization`, `home_weight_trends`, `post_activity_muscle_relaxation`, `nighttime_warmth_comfort`, `concert_hearing_protection`, `bedtime_pressure_blanket` | 12 |
| Lighting, smart home, and household control | `home_and_work` | `bedroom_lighting`, `first_automation`, `rental_security`, `heating_control`, `hallway_night_guidance`, `whole_home_alarm_refresh`, `laundry_leak_warning`, `apartment_floor_cleaning`, `renter_entry_lock`, `room_climate_measurement`, `appliance_energy_visibility`, `rental_window_shading` | 12 |
| DIY, tools, and household repair | `home_and_work` | `first_power_tool`, `essential_hand_tools`, `safe_high_reach`, `mounting_rental`, `first_home_saw`, `furniture_surface_prep`, `room_painting_setup`, `accurate_layout_tools`, `small_electronics_repair`, `under_sink_drip_repair`, `dust_eye_hearing_protection`, `portable_tool_storage` | 12 |
| Garden, patio, and outdoor home care | `home_and_work` | `small_lawn`, `water_smart_beds`, `all_weather_seating`, `humane_pest_control`, `pruning_small_yard`, `small_space_compost`, `balcony_container_garden`, `autumn_leaf_cleanup`, `removable_patio_shade`, `small_patio_cooking`, `hose_end_watering`, `bird_feeding_cleanup` | 12 |
| Music listening and home recording | `media_and_creativity` | `physical_music`, `small_room_mixing`, `voice_recording`, `first_instrument`, `first_audio_interface`, `compact_midi_control`, `portable_ambient_recording`, `bedroom_acoustic_control`, `quiet_guitar_amplification`, `timing_and_tuning_tools`, `sustain_pedal_and_stand`, `wood_instrument_storage` | 12 |
| Movies, television, and home theater | `media_and_creativity` | `bright_living_room_tv`, `rental_big_screen`, `clear_dialogue`, `streaming_upgrade`, `low_latency_console_display`, `shared_room_accessible_audio`, `backyard_movie_nights`, `physical_disc_library`, `small_room_music_movies`, `dorm_private_screen`, `cord_cutting_local_channels`, `family_media_control` | 12 |
| Reading, note-taking, and writing tools | `media_and_creativity` | `commuter_reader`, `meeting_notes`, `everyday_pen`, `night_reading_light`, `graduate_article_annotation`, `archival_personal_journal`, `manuscript_revision`, `multilingual_vocabulary_reader`, `story_planning_workspace`, `home_book_preservation`, `shared_family_audiobooks`, `portable_letter_writing` | 12 |
| Personal finance and household planning | `finance_and_decisions` | `household_budget`, `debt_or_savings`, `tax_help`, `first_investing_plan`, `couple_account_structure`, `annual_expense_sinking_funds`, `child_allowance_system`, `subscription_cost_audit`, `household_document_archive`, `cash_flow_payday_mismatch`, `charitable_giving_plan`, `major_purchase_comparison` | 12 |
| AI, machine learning, and computing choices | `science_and_technology` | `first_ml_compute`, `learning_path`, `local_ai_machine`, `research_data_storage`, `edge_vision_prototype`, `dataset_labeling_station`, `quiet_gpu_cooling`, `field_model_demo`, `ml_math_study_tools`, `collaborative_experiment_tracking`, `training_power_protection`, `responsible_model_testing` | 12 |
| Science, space, and education kits | `science_and_technology` | `family_astronomy`, `school_microscopy`, `local_weather`, `robotics_learning`, `backyard_bird_observation`, `rock_mineral_study`, `safe_home_chemistry`, `beginner_electronics_measurement`, `night_sky_navigation`, `insect_field_observation`, `sound_wave_classroom`, `solar_energy_experiment` | 12 |
| Digital privacy and practical security | `science_and_technology` | `account_security`, `private_backup`, `home_camera_privacy`, `phone_privacy_lifespan`, `home_router_controls`, `paper_identity_disposal`, `public_charging_travel`, `remote_work_screen_privacy`, `smart_speaker_household`, `retiring_old_devices`, `rental_door_access`, `shared_family_computer` | 12 |
| Urban living, commuting, and local preparedness | `society_and_place` | `five_mile_commute`, `rainy_city_commute`, `smoke_days`, `apartment_outage`, `car_free_grocery_run`, `street_bicycle_security`, `night_commute_visibility`, `transit_noise_commute`, `apartment_package_delivery`, `summer_heat_commute`, `winter_sidewalk_traction`, `offline_city_navigation` | 12 |
| Art, design, and creative tools | `media_and_creativity` | `digital_drawing`, `family_photo_prints`, `first_paint_medium`, `color_accurate_editing`, `home_artwork_scanning`, `plein_air_painting`, `small_space_printmaking`, `stop_motion_projects`, `sewing_first_workstation`, `calligraphy_practice`, `rotating_art_display`, `craft_cutting_workspace` | 12 |
| Sustainable consumption and repairability | `society_and_place` | `household_batteries`, `failing_appliance`, `reusable_lunch`, `outage_lighting`, `clothing_repair_kit`, `daily_drink_container`, `low_waste_cleaning`, `used_furniture_choice`, `apartment_food_scraps`, `shared_repair_toolbox`, `air_drying_laundry`, `standby_power_control` | 12 |

## Public-query audit

- Word count: min 87, median 120.0, mean 117.3, max 141
- Hard-rule failures: 0
- High-similarity pairs at Jaccard >= 0.78: 0
- Maximum pairwise Jaccard: 0.5081

## Frozen-world source probe

- Packs passing all shopping/community/wiki/forum probes: 28/28
- Failed packs: none
- Magento discovery probes passed: 336/336
- Postmill discovery probes passed: 336/336
- Kiwix discovery probes passed: 336/336
- Postmill probes using a recorded focused fallback: 288
- Shortest resolved Postmill discovery query: 2 words
- Kiwix probes using a recorded focused fallback: 22

Probe success proves only that each angle has live discovery roots and a sufficiently
populated source neighborhood in the frozen world. It is not a substitute for exact
fact-span verification or an answerability proof.

## Required promotion path

1. Build query-specific Evidence Records and a verified Evidence Graph for each angle.
2. Obtain two independent approvals for exact support spans and adjudicate disagreements.
3. Compile a fresh GeneratorView from the approved graph and render with the registered,
   version-pinned generator and the three frozen human-approved few-shots.
4. Run the blind GeneratorView-plus-Query review; regenerate failures and discard repeated
   failures.
5. Freeze only the surviving subset as formal tasks with hidden answerability proofs.

## Files

- `queries.jsonl`: full candidate records and private construction probes.
- `queries.csv`: review-friendly flat export.
- `source_probe_report.json`: live Magento/Postmill/Kiwix and registry checks.
- `audit_report.json`: distributions, hard-rule failures, and similarity audit.
- `topic_packs.json`: the 28-pack, 336-angle construction matrix.
- `manifest.json`: content hashes for this deterministic candidate-bank build.
