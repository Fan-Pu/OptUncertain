\ Model multi_agent_many_to_many
\ LP format - for model browsing. Use MPS format to capture full model detail.
Maximize
  - 0.00790871826590571 x_9_18_agent0 - 0.0116819140262588 x_9_40_agent0
   - 0.0106511569062948 x_9_41_agent0 - 0.00584720402597768 x_16_0_agent0
   - 0.00352956225927071 x_16_32_agent0
   - 0.00915812083555905 x_16_35_agent0 - 0.00790871826590571 x_9_18_agent1
   - 0.0116819140262588 x_9_40_agent1 - 0.0106511569062948 x_9_41_agent1
   - 0.00584720402597768 x_16_0_agent1 - 0.00352956225927071 x_16_32_agent1
   - 0.00915812083555905 x_16_35_agent1 + 0 u_0_agent0 + 0 u_18_agent0
   + 0 u_32_agent0 + 0 u_35_agent0 + 0 u_40_agent0 + 0 u_41_agent0
   + 0 u_100_agent0 - 0.005555 y_101_agent0 + 0 u_101_agent0
   + 0 u_200_agent0 - 0.005555 y_201_agent0 + 0 u_201_agent0 + 0 u_0_agent1
   + 0 u_18_agent1 + 0 u_32_agent1 + 0 u_35_agent1 + 0 u_40_agent1
   + 0 u_41_agent1 + 0 u_100_agent1 - 0.005555 y_101_agent1
   + 0 u_101_agent1 + 0 u_200_agent1 - 0.005555 y_201_agent1
   + 0 u_201_agent1 + 0.0790044444444445 alpha_0_1_agent0
   + 0.0395022222222222 alpha_18_1_agent0
   + 0.0395022222222222 alpha_32_1_agent0
   + 0.0395022222222222 alpha_35_1_agent0
   + 0.0790044444444445 alpha_40_1_agent0
   + 0.0790044444444445 alpha_41_1_agent0 + 0.2222 alpha_100_1_agent0
   + 0.04444 alpha_101_1_agent0 + 0.05555 alpha_200_1_agent0
   + 0.08888 alpha_201_1_agent0 + 0.0790044444444445 alpha_0_1_agent1
   + 0.0395022222222222 alpha_18_1_agent1
   + 0.0395022222222222 alpha_32_1_agent1
   + 0.0395022222222222 alpha_35_1_agent1
   + 0.0790044444444445 alpha_40_1_agent1
   + 0.0790044444444445 alpha_41_1_agent1 + 0.2222 alpha_100_1_agent1
   + 0.04444 alpha_101_1_agent1 + 0.05555 alpha_200_1_agent1
   + 0.08888 alpha_201_1_agent1 + 0.0114382805251764 Constant
Subject To
 depart_agent0: x_16_0_agent0 + x_16_32_agent0 + x_16_35_agent0 = 1
 first_hop_vp_agent0: x_16_0_agent0 + x_16_32_agent0 + x_16_35_agent0 = 1
 no_return_agent0: = 0
 flow_in_0_agent0: x_16_0_agent0 - y_0_agent0 = 0
 flow_out_0_agent0: - y_0_agent0 <= 0
 flow_in_18_agent0: x_9_18_agent0 - y_18_agent0 = 0
 flow_out_18_agent0: - y_18_agent0 <= 0
 flow_in_32_agent0: x_16_32_agent0 - y_32_agent0 = 0
 flow_out_32_agent0: - y_32_agent0 <= 0
 flow_in_35_agent0: x_16_35_agent0 - y_35_agent0 = 0
 flow_out_35_agent0: - y_35_agent0 <= 0
 flow_in_40_agent0: x_9_40_agent0 - y_40_agent0 = 0
 flow_out_40_agent0: - y_40_agent0 <= 0
 flow_in_41_agent0: x_9_41_agent0 - y_41_agent0 = 0
 flow_out_41_agent0: - y_41_agent0 <= 0
 flow_in_100_agent0: - y_100_agent0 = 0
 flow_out_100_agent0: - y_100_agent0 <= 0
 flow_in_101_agent0: - y_101_agent0 = 0
 flow_out_101_agent0: - y_101_agent0 <= 0
 flow_in_200_agent0: - y_200_agent0 = 0
 flow_out_200_agent0: - y_200_agent0 <= 0
 flow_in_201_agent0: - y_201_agent0 = 0
 flow_out_201_agent0: - y_201_agent0 <= 0
 open_path_agent0: - y_0_agent0 - y_18_agent0 - y_32_agent0 - y_35_agent0
   - y_40_agent0 - y_41_agent0 - y_100_agent0 - y_101_agent0 - y_200_agent0
   - y_201_agent0 = -1
 depart_agent1: x_9_18_agent1 + x_9_40_agent1 + x_9_41_agent1 = 1
 first_hop_vp_agent1: x_9_18_agent1 + x_9_40_agent1 + x_9_41_agent1 = 1
 no_return_agent1: = 0
 flow_in_0_agent1: x_16_0_agent1 - y_0_agent1 = 0
 flow_out_0_agent1: - y_0_agent1 <= 0
 flow_in_18_agent1: x_9_18_agent1 - y_18_agent1 = 0
 flow_out_18_agent1: - y_18_agent1 <= 0
 flow_in_32_agent1: x_16_32_agent1 - y_32_agent1 = 0
 flow_out_32_agent1: - y_32_agent1 <= 0
 flow_in_35_agent1: x_16_35_agent1 - y_35_agent1 = 0
 flow_out_35_agent1: - y_35_agent1 <= 0
 flow_in_40_agent1: x_9_40_agent1 - y_40_agent1 = 0
 flow_out_40_agent1: - y_40_agent1 <= 0
 flow_in_41_agent1: x_9_41_agent1 - y_41_agent1 = 0
 flow_out_41_agent1: - y_41_agent1 <= 0
 flow_in_100_agent1: - y_100_agent1 = 0
 flow_out_100_agent1: - y_100_agent1 <= 0
 flow_in_101_agent1: - y_101_agent1 = 0
 flow_out_101_agent1: - y_101_agent1 <= 0
 flow_in_200_agent1: - y_200_agent1 = 0
 flow_out_200_agent1: - y_200_agent1 <= 0
 flow_in_201_agent1: - y_201_agent1 = 0
 flow_out_201_agent1: - y_201_agent1 <= 0
 open_path_agent1: - y_0_agent1 - y_18_agent1 - y_32_agent1 - y_35_agent1
   - y_40_agent1 - y_41_agent1 - y_100_agent1 - y_101_agent1 - y_200_agent1
   - y_201_agent1 = -1
 alpha_link_0_0_agent0: alpha_0_0_agent0 <= 0
 alpha_link_0_1_agent0: - y_0_agent0 + alpha_0_1_agent0 <= 0
 alpha_link_18_0_agent0: alpha_18_0_agent0 <= 0
 alpha_link_18_1_agent0: - y_18_agent0 + alpha_18_1_agent0 <= 0
 alpha_link_32_0_agent0: alpha_32_0_agent0 <= 0
 alpha_link_32_1_agent0: - y_32_agent0 + alpha_32_1_agent0 <= 0
 alpha_link_35_0_agent0: alpha_35_0_agent0 <= 0
 alpha_link_35_1_agent0: - y_35_agent0 + alpha_35_1_agent0 <= 0
 alpha_link_40_0_agent0: alpha_40_0_agent0 <= 0
 alpha_link_40_1_agent0: - y_40_agent0 + alpha_40_1_agent0 <= 0
 alpha_link_41_0_agent0: alpha_41_0_agent0 <= 0
 alpha_link_41_1_agent0: - y_41_agent0 + alpha_41_1_agent0 <= 0
 alpha_link_100_0_agent0: alpha_100_0_agent0 <= 0
 alpha_link_100_1_agent0: - y_100_agent0 + alpha_100_1_agent0 <= 0
 alpha_link_101_0_agent0: alpha_101_0_agent0 <= 0
 alpha_link_101_1_agent0: - y_101_agent0 + alpha_101_1_agent0 <= 0
 alpha_link_200_0_agent0: alpha_200_0_agent0 <= 0
 alpha_link_200_1_agent0: - y_200_agent0 + alpha_200_1_agent0 <= 0
 alpha_link_201_0_agent0: alpha_201_0_agent0 <= 0
 alpha_link_201_1_agent0: - y_201_agent0 + alpha_201_1_agent0 <= 0
 alpha_link_0_0_agent1: alpha_0_0_agent1 <= 0
 alpha_link_0_1_agent1: - y_0_agent1 + alpha_0_1_agent1 <= 0
 alpha_link_18_0_agent1: alpha_18_0_agent1 <= 0
 alpha_link_18_1_agent1: - y_18_agent1 + alpha_18_1_agent1 <= 0
 alpha_link_32_0_agent1: alpha_32_0_agent1 <= 0
 alpha_link_32_1_agent1: - y_32_agent1 + alpha_32_1_agent1 <= 0
 alpha_link_35_0_agent1: alpha_35_0_agent1 <= 0
 alpha_link_35_1_agent1: - y_35_agent1 + alpha_35_1_agent1 <= 0
 alpha_link_40_0_agent1: alpha_40_0_agent1 <= 0
 alpha_link_40_1_agent1: - y_40_agent1 + alpha_40_1_agent1 <= 0
 alpha_link_41_0_agent1: alpha_41_0_agent1 <= 0
 alpha_link_41_1_agent1: - y_41_agent1 + alpha_41_1_agent1 <= 0
 alpha_link_100_0_agent1: alpha_100_0_agent1 <= 0
 alpha_link_100_1_agent1: - y_100_agent1 + alpha_100_1_agent1 <= 0
 alpha_link_101_0_agent1: alpha_101_0_agent1 <= 0
 alpha_link_101_1_agent1: - y_101_agent1 + alpha_101_1_agent1 <= 0
 alpha_link_200_0_agent1: alpha_200_0_agent1 <= 0
 alpha_link_200_1_agent1: - y_200_agent1 + alpha_200_1_agent1 <= 0
 alpha_link_201_0_agent1: alpha_201_0_agent1 <= 0
 alpha_link_201_1_agent1: - y_201_agent1 + alpha_201_1_agent1 <= 0
 unique_target_0: alpha_0_0_agent0 + alpha_18_0_agent0 + alpha_32_0_agent0
   + alpha_35_0_agent0 + alpha_40_0_agent0 + alpha_41_0_agent0
   + alpha_100_0_agent0 + alpha_101_0_agent0 + alpha_200_0_agent0
   + alpha_201_0_agent0 + alpha_0_0_agent1 + alpha_18_0_agent1
   + alpha_32_0_agent1 + alpha_35_0_agent1 + alpha_40_0_agent1
   + alpha_41_0_agent1 + alpha_100_0_agent1 + alpha_101_0_agent1
   + alpha_200_0_agent1 + alpha_201_0_agent1 <= 0
 unique_target_1: alpha_0_1_agent0 + alpha_18_1_agent0 + alpha_32_1_agent0
   + alpha_35_1_agent0 + alpha_40_1_agent0 + alpha_41_1_agent0
   + alpha_100_1_agent0 + alpha_101_1_agent0 + alpha_200_1_agent0
   + alpha_201_1_agent0 + alpha_0_1_agent1 + alpha_18_1_agent1
   + alpha_32_1_agent1 + alpha_35_1_agent1 + alpha_40_1_agent1
   + alpha_41_1_agent1 + alpha_100_1_agent1 + alpha_101_1_agent1
   + alpha_200_1_agent1 + alpha_201_1_agent1 <= 1
Bounds
 1 <= u_0_agent0 <= 10
 1 <= u_18_agent0 <= 10
 1 <= u_32_agent0 <= 10
 1 <= u_35_agent0 <= 10
 1 <= u_40_agent0 <= 10
 1 <= u_41_agent0 <= 10
 1 <= u_100_agent0 <= 10
 1 <= u_101_agent0 <= 10
 1 <= u_200_agent0 <= 10
 1 <= u_201_agent0 <= 10
 1 <= u_0_agent1 <= 10
 1 <= u_18_agent1 <= 10
 1 <= u_32_agent1 <= 10
 1 <= u_35_agent1 <= 10
 1 <= u_40_agent1 <= 10
 1 <= u_41_agent1 <= 10
 1 <= u_100_agent1 <= 10
 1 <= u_101_agent1 <= 10
 1 <= u_200_agent1 <= 10
 1 <= u_201_agent1 <= 10
 Constant = 1
Binaries
 x_9_18_agent0 x_9_40_agent0 x_9_41_agent0 x_16_0_agent0 x_16_32_agent0
 x_16_35_agent0 x_9_18_agent1 x_9_40_agent1 x_9_41_agent1 x_16_0_agent1
 x_16_32_agent1 x_16_35_agent1 y_0_agent0 y_18_agent0 y_32_agent0
 y_35_agent0 y_40_agent0 y_41_agent0 y_100_agent0 y_101_agent0 y_200_agent0
 y_201_agent0 y_0_agent1 y_18_agent1 y_32_agent1 y_35_agent1 y_40_agent1
 y_41_agent1 y_100_agent1 y_101_agent1 y_200_agent1 y_201_agent1
 alpha_0_0_agent0 alpha_0_1_agent0 alpha_18_0_agent0 alpha_18_1_agent0
 alpha_32_0_agent0 alpha_32_1_agent0 alpha_35_0_agent0 alpha_35_1_agent0
 alpha_40_0_agent0 alpha_40_1_agent0 alpha_41_0_agent0 alpha_41_1_agent0
 alpha_100_0_agent0 alpha_100_1_agent0 alpha_101_0_agent0
 alpha_101_1_agent0 alpha_200_0_agent0 alpha_200_1_agent0
 alpha_201_0_agent0 alpha_201_1_agent0 alpha_0_0_agent1 alpha_0_1_agent1
 alpha_18_0_agent1 alpha_18_1_agent1 alpha_32_0_agent1 alpha_32_1_agent1
 alpha_35_0_agent1 alpha_35_1_agent1 alpha_40_0_agent1 alpha_40_1_agent1
 alpha_41_0_agent1 alpha_41_1_agent1 alpha_100_0_agent1 alpha_100_1_agent1
 alpha_101_0_agent1 alpha_101_1_agent1 alpha_200_0_agent1
 alpha_200_1_agent1 alpha_201_0_agent1 alpha_201_1_agent1
End
