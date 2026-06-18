\ Model multi_agent_many_to_many
\ LP format - for model browsing. Use MPS format to capture full model detail.
\ Signature: 0x377f65a3b8b9805b
Maximize multi-objectives
  target_directed_reward: Priority=2 Weight=1 AbsTol=0 RelTol=0
   0 u_50_agent0 + 0 u_51_agent0 + 0 u_52_agent0 + 0 u_53_agent0
   + 0.5555555555555556 z_0_7_agent0 + 0.5 z_1_7_agent0 + 0.5 z_2_7_agent0
   + 0.5 z_3_7_agent0 + 0.5 z_7_7_agent0 + 0.4444444444444445 z_0_11_agent0
   + 0.5 z_1_11_agent0 + 0.5 z_2_11_agent0 + 0.5 z_3_11_agent0
   + 0.5 z_7_11_agent0
  target_directed_route_cost: Priority=1 Weight=1 AbsTol=0 RelTol=0
   - 0.00469444064395494 x_0_11_agent0 - 0.00515574405983491 x_0_15_agent0
   - 0.00349466411273772 x_0_18_agent0 - 0.0041342864961007 x_4_44_agent0
   - 0.00691761298855293 x_4_47_agent0 - 0.00646212432161262 x_7_10_agent0
   - 0.00473902038582569 x_8_9_agent0 - 0.00447348018424773 x_8_31_agent0
   - 0.00473902038582569 x_9_8_agent0 - 0.00309926118484061 x_9_42_agent0
   - 0.00646212432161262 x_10_7_agent0 - 0.00772198659187303 x_10_22_agent0
   - 0.00469444064395494 x_11_0_agent0 - 0.00410521275140238 x_13_15_agent0
   - 0.00257787202991745 x_13_18_agent0
   - 0.00276975874492635 x_13_44_agent0 - 0.00515574405983491 x_15_0_agent0
   - 0.00410521275140238 x_15_13_agent0
   - 0.00191111415150271 x_15_18_agent0
   - 0.00563836822182697 x_15_22_agent0
   - 0.00280658548821088 x_15_33_agent0 - 0.00349466411273772 x_18_0_agent0
   - 0.00257787202991745 x_18_13_agent0
   - 0.00191111415150271 x_18_15_agent0
   - 0.00435330870616135 x_18_33_agent0
   - 0.00772198659187303 x_22_10_agent0
   - 0.00563836822182697 x_22_15_agent0 - 0.00447348018424773 x_31_8_agent0
   - 0.00842363296392576 x_31_42_agent0
   - 0.00594267341633603 x_32_44_agent0 - 0.003201988416108 x_32_47_agent0
   - 0.00280658548821088 x_33_15_agent0
   - 0.00435330870616135 x_33_18_agent0
   - 0.00296358370958179 x_33_34_agent0
   - 0.00296358370958179 x_34_33_agent0
   - 0.00480879737310166 x_34_42_agent0 - 0.00309926118484061 x_42_9_agent0
   - 0.00842363296392576 x_42_31_agent0
   - 0.00480879737310166 x_42_34_agent0 - 0.0041342864961007 x_44_4_agent0
   - 0.00276975874492635 x_44_13_agent0
   - 0.00594267341633603 x_44_32_agent0
   - 0.00577404569708579 x_44_47_agent0 - 0.00691761298855293 x_47_4_agent0
   - 0.003201988416108 x_47_32_agent0 - 0.00577404569708579 x_47_44_agent0
   - 0.01 y_0_agent0 - 0.01 y_4_agent0 - 0.01 y_8_agent0 - 0.02 y_9_agent0
   - 0.01 y_10_agent0 - 0.04 y_15_agent0 - 0.02 y_18_agent0
   - 0.02 y_22_agent0 - 0.01 y_31_agent0 - 0.01 y_32_agent0
   - 0.04 y_33_agent0 - 0.03 y_34_agent0 - 0.03 y_42_agent0
   - 0.05 y_44_agent0 - 0.01 y_47_agent0 + 0.0225778720299175 Constant1
Subject To
 depart_agent0: x_13_15_agent0 + x_13_18_agent0 + x_13_44_agent0 = 1
 first_hop_vp_agent0: x_13_15_agent0 + x_13_18_agent0 + x_13_44_agent0 = 1
 first_hop_grounded_vv_agent0: x_13_15_agent0 + x_13_18_agent0
   + x_13_44_agent0 = 1
 no_return_agent0: x_15_13_agent0 + x_18_13_agent0 + x_44_13_agent0 = 0
 flow_in_0_agent0: x_11_0_agent0 + x_15_0_agent0 + x_18_0_agent0
   - y_0_agent0 = 0
 flow_out_0_agent0: x_0_11_agent0 + x_0_15_agent0 + x_0_18_agent0
   - y_0_agent0 <= 0
 flow_in_4_agent0: x_44_4_agent0 + x_47_4_agent0 - y_4_agent0 = 0
 flow_out_4_agent0: x_4_44_agent0 + x_4_47_agent0 - y_4_agent0 <= 0
 flow_in_7_agent0: x_10_7_agent0 - y_7_agent0 = 0
 flow_out_7_agent0: x_7_10_agent0 - y_7_agent0 <= 0
 flow_in_8_agent0: x_9_8_agent0 + x_31_8_agent0 - y_8_agent0 = 0
 flow_out_8_agent0: x_8_9_agent0 + x_8_31_agent0 - y_8_agent0 <= 0
 flow_in_9_agent0: x_8_9_agent0 + x_42_9_agent0 - y_9_agent0 = 0
 flow_out_9_agent0: x_9_8_agent0 + x_9_42_agent0 - y_9_agent0 <= 0
 flow_in_10_agent0: x_7_10_agent0 + x_22_10_agent0 - y_10_agent0 = 0
 flow_out_10_agent0: x_10_7_agent0 + x_10_22_agent0 - y_10_agent0 <= 0
 flow_in_11_agent0: x_0_11_agent0 - y_11_agent0 = 0
 flow_out_11_agent0: x_11_0_agent0 - y_11_agent0 <= 0
 flow_in_15_agent0: x_0_15_agent0 + x_13_15_agent0 + x_18_15_agent0
   + x_22_15_agent0 + x_33_15_agent0 - y_15_agent0 = 0
 flow_out_15_agent0: x_15_0_agent0 + x_15_13_agent0 + x_15_18_agent0
   + x_15_22_agent0 + x_15_33_agent0 - y_15_agent0 <= 0
 flow_in_18_agent0: x_0_18_agent0 + x_13_18_agent0 + x_15_18_agent0
   + x_33_18_agent0 - y_18_agent0 = 0
 flow_out_18_agent0: x_18_0_agent0 + x_18_13_agent0 + x_18_15_agent0
   + x_18_33_agent0 - y_18_agent0 <= 0
 flow_in_22_agent0: x_10_22_agent0 + x_15_22_agent0 - y_22_agent0 = 0
 flow_out_22_agent0: x_22_10_agent0 + x_22_15_agent0 - y_22_agent0 <= 0
 flow_in_31_agent0: x_8_31_agent0 + x_42_31_agent0 - y_31_agent0 = 0
 flow_out_31_agent0: x_31_8_agent0 + x_31_42_agent0 - y_31_agent0 <= 0
 flow_in_32_agent0: x_44_32_agent0 + x_47_32_agent0 - y_32_agent0 = 0
 flow_out_32_agent0: x_32_44_agent0 + x_32_47_agent0 - y_32_agent0 <= 0
 flow_in_33_agent0: x_15_33_agent0 + x_18_33_agent0 + x_34_33_agent0
   - y_33_agent0 = 0
 flow_out_33_agent0: x_33_15_agent0 + x_33_18_agent0 + x_33_34_agent0
   - y_33_agent0 <= 0
 flow_in_34_agent0: x_33_34_agent0 + x_42_34_agent0 - y_34_agent0 = 0
 flow_out_34_agent0: x_34_33_agent0 + x_34_42_agent0 - y_34_agent0 <= 0
 flow_in_42_agent0: x_9_42_agent0 + x_31_42_agent0 + x_34_42_agent0
   - y_42_agent0 = 0
 flow_out_42_agent0: x_42_9_agent0 + x_42_31_agent0 + x_42_34_agent0
   - y_42_agent0 <= 0
 flow_in_44_agent0: x_4_44_agent0 + x_13_44_agent0 + x_32_44_agent0
   + x_47_44_agent0 - y_44_agent0 = 0
 flow_out_44_agent0: x_44_4_agent0 + x_44_13_agent0 + x_44_32_agent0
   + x_44_47_agent0 - y_44_agent0 <= 0
 flow_in_47_agent0: x_4_47_agent0 + x_32_47_agent0 + x_44_47_agent0
   - y_47_agent0 = 0
 flow_out_47_agent0: x_47_4_agent0 + x_47_32_agent0 + x_47_44_agent0
   - y_47_agent0 <= 0
 flow_in_50_agent0: - y_50_agent0 = 0
 flow_out_50_agent0: - y_50_agent0 <= 0
 flow_in_51_agent0: - y_51_agent0 = 0
 flow_out_51_agent0: - y_51_agent0 <= 0
 flow_in_52_agent0: - y_52_agent0 = 0
 flow_out_52_agent0: - y_52_agent0 <= 0
 flow_in_53_agent0: - y_53_agent0 = 0
 flow_out_53_agent0: - y_53_agent0 <= 0
 target_reward_visit_0_7_agent0: - y_7_agent0 + z_0_7_agent0 <= 0
 target_reward_visit_1_7_agent0: - y_7_agent0 + z_1_7_agent0 <= 0
 target_reward_visit_2_7_agent0: - y_7_agent0 + z_2_7_agent0 <= 0
 target_reward_visit_3_7_agent0: - y_7_agent0 + z_3_7_agent0 <= 0
 target_reward_visit_4_7_agent0: - y_7_agent0 + z_4_7_agent0 <= 0
 target_reward_visit_5_7_agent0: - y_7_agent0 + z_5_7_agent0 <= 0
 target_reward_visit_6_7_agent0: - y_7_agent0 + z_6_7_agent0 <= 0
 target_reward_visit_7_7_agent0: - y_7_agent0 + z_7_7_agent0 <= 0
 target_reward_visit_0_11_agent0: - y_11_agent0 + z_0_11_agent0 <= 0
 target_reward_visit_1_11_agent0: - y_11_agent0 + z_1_11_agent0 <= 0
 target_reward_visit_2_11_agent0: - y_11_agent0 + z_2_11_agent0 <= 0
 target_reward_visit_3_11_agent0: - y_11_agent0 + z_3_11_agent0 <= 0
 target_reward_visit_4_11_agent0: - y_11_agent0 + z_4_11_agent0 <= 0
 target_reward_visit_5_11_agent0: - y_11_agent0 + z_5_11_agent0 <= 0
 target_reward_visit_6_11_agent0: - y_11_agent0 + z_6_11_agent0 <= 0
 target_reward_visit_7_11_agent0: - y_11_agent0 + z_7_11_agent0 <= 0
 mtz_0_11_agent0: 22 x_0_11_agent0 + u_0_agent0 - u_11_agent0 <= 21
 mtz_0_15_agent0: 22 x_0_15_agent0 + u_0_agent0 - u_15_agent0 <= 21
 mtz_0_18_agent0: 22 x_0_18_agent0 + u_0_agent0 - u_18_agent0 <= 21
 mtz_4_44_agent0: 22 x_4_44_agent0 + u_4_agent0 - u_44_agent0 <= 21
 mtz_4_47_agent0: 22 x_4_47_agent0 + u_4_agent0 - u_47_agent0 <= 21
 mtz_7_10_agent0: 22 x_7_10_agent0 + u_7_agent0 - u_10_agent0 <= 21
 mtz_8_9_agent0: 22 x_8_9_agent0 + u_8_agent0 - u_9_agent0 <= 21
 mtz_8_31_agent0: 22 x_8_31_agent0 + u_8_agent0 - u_31_agent0 <= 21
 mtz_9_8_agent0: 22 x_9_8_agent0 - u_8_agent0 + u_9_agent0 <= 21
 mtz_9_42_agent0: 22 x_9_42_agent0 + u_9_agent0 - u_42_agent0 <= 21
 mtz_10_7_agent0: 22 x_10_7_agent0 - u_7_agent0 + u_10_agent0 <= 21
 mtz_10_22_agent0: 22 x_10_22_agent0 + u_10_agent0 - u_22_agent0 <= 21
 mtz_11_0_agent0: 22 x_11_0_agent0 - u_0_agent0 + u_11_agent0 <= 21
 mtz_13_15_agent0: 22 x_13_15_agent0 + u_13_agent0 - u_15_agent0 <= 21
 mtz_13_18_agent0: 22 x_13_18_agent0 + u_13_agent0 - u_18_agent0 <= 21
 mtz_13_44_agent0: 22 x_13_44_agent0 + u_13_agent0 - u_44_agent0 <= 21
 mtz_15_0_agent0: 22 x_15_0_agent0 - u_0_agent0 + u_15_agent0 <= 21
 mtz_15_13_agent0: 22 x_15_13_agent0 - u_13_agent0 + u_15_agent0 <= 21
 mtz_15_18_agent0: 22 x_15_18_agent0 + u_15_agent0 - u_18_agent0 <= 21
 mtz_15_22_agent0: 22 x_15_22_agent0 + u_15_agent0 - u_22_agent0 <= 21
 mtz_15_33_agent0: 22 x_15_33_agent0 + u_15_agent0 - u_33_agent0 <= 21
 mtz_18_0_agent0: 22 x_18_0_agent0 - u_0_agent0 + u_18_agent0 <= 21
 mtz_18_13_agent0: 22 x_18_13_agent0 - u_13_agent0 + u_18_agent0 <= 21
 mtz_18_15_agent0: 22 x_18_15_agent0 - u_15_agent0 + u_18_agent0 <= 21
 mtz_18_33_agent0: 22 x_18_33_agent0 + u_18_agent0 - u_33_agent0 <= 21
 mtz_22_10_agent0: 22 x_22_10_agent0 - u_10_agent0 + u_22_agent0 <= 21
 mtz_22_15_agent0: 22 x_22_15_agent0 - u_15_agent0 + u_22_agent0 <= 21
 mtz_31_8_agent0: 22 x_31_8_agent0 - u_8_agent0 + u_31_agent0 <= 21
 mtz_31_42_agent0: 22 x_31_42_agent0 + u_31_agent0 - u_42_agent0 <= 21
 mtz_32_44_agent0: 22 x_32_44_agent0 + u_32_agent0 - u_44_agent0 <= 21
 mtz_32_47_agent0: 22 x_32_47_agent0 + u_32_agent0 - u_47_agent0 <= 21
 mtz_33_15_agent0: 22 x_33_15_agent0 - u_15_agent0 + u_33_agent0 <= 21
 mtz_33_18_agent0: 22 x_33_18_agent0 - u_18_agent0 + u_33_agent0 <= 21
 mtz_33_34_agent0: 22 x_33_34_agent0 + u_33_agent0 - u_34_agent0 <= 21
 mtz_34_33_agent0: 22 x_34_33_agent0 - u_33_agent0 + u_34_agent0 <= 21
 mtz_34_42_agent0: 22 x_34_42_agent0 + u_34_agent0 - u_42_agent0 <= 21
 mtz_42_9_agent0: 22 x_42_9_agent0 - u_9_agent0 + u_42_agent0 <= 21
 mtz_42_31_agent0: 22 x_42_31_agent0 - u_31_agent0 + u_42_agent0 <= 21
 mtz_42_34_agent0: 22 x_42_34_agent0 - u_34_agent0 + u_42_agent0 <= 21
 mtz_44_4_agent0: 22 x_44_4_agent0 - u_4_agent0 + u_44_agent0 <= 21
 mtz_44_13_agent0: 22 x_44_13_agent0 - u_13_agent0 + u_44_agent0 <= 21
 mtz_44_32_agent0: 22 x_44_32_agent0 - u_32_agent0 + u_44_agent0 <= 21
 mtz_44_47_agent0: 22 x_44_47_agent0 + u_44_agent0 - u_47_agent0 <= 21
 mtz_47_4_agent0: 22 x_47_4_agent0 - u_4_agent0 + u_47_agent0 <= 21
 mtz_47_32_agent0: 22 x_47_32_agent0 - u_32_agent0 + u_47_agent0 <= 21
 mtz_47_44_agent0: 22 x_47_44_agent0 - u_44_agent0 + u_47_agent0 <= 21
 target_reward_positive_4_7_agent0: z_4_7_agent0 = 0
 target_reward_positive_4_11_agent0: z_4_11_agent0 = 0
 target_reward_positive_5_7_agent0: z_5_7_agent0 = 0
 target_reward_positive_5_11_agent0: z_5_11_agent0 = 0
 target_reward_positive_6_7_agent0: z_6_7_agent0 = 0
 target_reward_positive_6_11_agent0: z_6_11_agent0 = 0
 target_reward_unique_0: z_0_7_agent0 + z_0_11_agent0 = 1
 target_reward_unique_1: z_1_7_agent0 + z_1_11_agent0 = 1
 target_reward_unique_2: z_2_7_agent0 + z_2_11_agent0 = 1
 target_reward_unique_3: z_3_7_agent0 + z_3_11_agent0 = 1
 target_reward_found_4: z_4_7_agent0 + z_4_11_agent0 = 0
 target_reward_found_5: z_5_7_agent0 + z_5_11_agent0 = 0
 target_reward_found_6: z_6_7_agent0 + z_6_11_agent0 = 0
 target_reward_unique_7: z_7_7_agent0 + z_7_11_agent0 = 1
 target_directed_agent_assignment_agent0: z_0_7_agent0 + z_1_7_agent0
   + z_2_7_agent0 + z_3_7_agent0 + z_7_7_agent0 + z_0_11_agent0
   + z_1_11_agent0 + z_2_11_agent0 + z_3_11_agent0 + z_7_11_agent0 >= 1
Bounds
 1 <= u_0_agent0 <= 22
 1 <= u_4_agent0 <= 22
 1 <= u_7_agent0 <= 22
 1 <= u_8_agent0 <= 22
 1 <= u_9_agent0 <= 22
 1 <= u_10_agent0 <= 22
 1 <= u_11_agent0 <= 22
 1 <= u_13_agent0 <= 22
 1 <= u_15_agent0 <= 22
 1 <= u_18_agent0 <= 22
 1 <= u_22_agent0 <= 22
 1 <= u_31_agent0 <= 22
 1 <= u_32_agent0 <= 22
 1 <= u_33_agent0 <= 22
 1 <= u_34_agent0 <= 22
 1 <= u_42_agent0 <= 22
 1 <= u_44_agent0 <= 22
 1 <= u_47_agent0 <= 22
 1 <= u_50_agent0 <= 22
 1 <= u_51_agent0 <= 22
 1 <= u_52_agent0 <= 22
 1 <= u_53_agent0 <= 22
 Constant1 = 1
Binaries
 x_0_11_agent0 x_0_15_agent0 x_0_18_agent0 x_4_44_agent0 x_4_47_agent0
 x_7_10_agent0 x_8_9_agent0 x_8_31_agent0 x_9_8_agent0 x_9_42_agent0
 x_10_7_agent0 x_10_22_agent0 x_11_0_agent0 x_13_15_agent0 x_13_18_agent0
 x_13_44_agent0 x_15_0_agent0 x_15_13_agent0 x_15_18_agent0 x_15_22_agent0
 x_15_33_agent0 x_18_0_agent0 x_18_13_agent0 x_18_15_agent0 x_18_33_agent0
 x_22_10_agent0 x_22_15_agent0 x_31_8_agent0 x_31_42_agent0 x_32_44_agent0
 x_32_47_agent0 x_33_15_agent0 x_33_18_agent0 x_33_34_agent0 x_34_33_agent0
 x_34_42_agent0 x_42_9_agent0 x_42_31_agent0 x_42_34_agent0 x_44_4_agent0
 x_44_13_agent0 x_44_32_agent0 x_44_47_agent0 x_47_4_agent0 x_47_32_agent0
 x_47_44_agent0 y_0_agent0 y_4_agent0 y_7_agent0 y_8_agent0 y_9_agent0
 y_10_agent0 y_11_agent0 y_15_agent0 y_18_agent0 y_22_agent0 y_31_agent0
 y_32_agent0 y_33_agent0 y_34_agent0 y_42_agent0 y_44_agent0 y_47_agent0
 y_50_agent0 y_51_agent0 y_52_agent0 y_53_agent0 z_0_7_agent0 z_1_7_agent0
 z_2_7_agent0 z_3_7_agent0 z_4_7_agent0 z_5_7_agent0 z_6_7_agent0
 z_7_7_agent0 z_0_11_agent0 z_1_11_agent0 z_2_11_agent0 z_3_11_agent0
 z_4_11_agent0 z_5_11_agent0 z_6_11_agent0 z_7_11_agent0
End
