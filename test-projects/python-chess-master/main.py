import time
from io import StringIO
import chess.pgn

def main():
    # Plug in a long PGN here for runtime scaling
    pgn_text = """
    [Event "Belgrade"]
    [Site "Belgrade YUG"]
    [Date "1989.02.17"]
    [White "Ivan Nikolic"]
    [Black "Goran Arsovic"]
    [Result "1/2-1/2"]
    [Variant "Standard"]
    [ECO "E95"]
    [Opening "King's Indian Defense: Orthodox Variation"]
    [Annotator "https://lichess.org/@/Prasaadh"]
    [StudyName "Longest chess game"]
    [ChapterName "Ivan Nikolic - Goran Arsovic"]
    [Source "https://lichess.org/study/2KLSpe04/9iJZwSvN"]
    [Orientation "white"]

    1. d4 Nf6 2. c4 g6 3. Nc3 Bg7 4. e4 d6 5. Nf3 O-O 6. Be2 Nbd7 7. O-O e5 8. Re1 Re8 9. Bf1 h6 10. d5 Nh7 11. Rb1 f5 12. Nd2 f4 13. b4 g5 14. Nb3 Bf8 15. Be2 Ndf6 16. c5 g4 17. cxd6 cxd6 18. a3 Ng5 19. Bf1 Re7 20. Qd3 Rg7 21. Kh1 Qe8 22. Nd2 g3 23. fxg3 fxg3 24. Qxg3 Nh3 25. Qf3 Qg6 26. Nc4 Bd7 27. Bd3 Ng5 28. Bxg5 Qxg5 29. Ne3 Re8 30. Ne2 Be7 31. Rbd1 Rf8 32. Nf5 Ng4 33. Neg3 h5 34. Kg1 h4 35. Qxg4 Qxg4 36. Nh6+ Kh7 37. Nxg4 hxg3 38. Ne3 gxh2+ 39. Kxh2 Rh8 40. Rh1 Kg6+ 41. Kg1 Rc8 42. Be2 Rc3 43. Rd3 Rc1+ 44. Nf1 Bd8 45. Rh8 Bb6+ 46. Kh2 Rh7+ 47. Rxh7 Kxh7 48. Nd2 Bg1+ 49. Kh1 Bd4+ 50. Nf1 Bg4 51. Bxg4 Rxf1+ 52. Kh2 Bg1+ 53. Kh3 Re1 54. Bf5+ Kh6 55. Kg4 Re3 56. Rd1 Bh2 57. Rh1 Rg3+ 58. Kh4 Rxg2 59. Kh3 Rg3+ 60. Kxh2 Rxa3 61. Rg1 Ra6 62. Rg6+ Kh5 63. Kg3 Rb6 64. Rg7 Rxb4 65. Bc8 a5 66. Bxb7 a4 67. Bc6 a3 68. Ra7 Rb3+ 69. Kf2 Kg5 70. Ke2 Kf4 71. Ra4 Rh3 72. Kd2 a2 73. Bb5 Rh1 74. Rxa2 Rh2+ 75. Be2 Kxe4 76. Ra5 Kd4 77. Ke1 Rh1+ 78. Kf2 Rc1 79. Bg4 Rc2+ 80. Ke1 e4 81. Be6 Ke5 82. Bg8 Rc8 83. Bf7 Rc7 84. Be6 Rc2 85. Ra8 Rb2 86. Ra6 Rg2 87. Kd1 Rb2 88. Ra5 Rg2 89. Bd7 Rh2 90. Bc6 Kf4 91. Ra8 e3 92. Re8 Kf3 93. Rf8+ Ke4 94. Rf6 Kd3 95. Bb5+ Kd4 96. Rf5 Rh1+ 97. Ke2 Rh2+ 98. Kd1 Rh1+ 99. Kc2 Rh2+ 100. Kc1 Rh1+ 101. Kc2 Rh2+ 102. Kd1 Rh1+ 103. Ke2 Rh2+ 104. Kf1 Rb2 105. Be2 Ke4 106. Rh5 Rb1+ 107. Kg2 Rb2 108. Rh4+ Kxd5 109. Kf3 Kc5 110. Kxe3 Rb3+ 111. Bd3 d5 112. Rh8 Ra3 113. Re8 Kd6 114. Kd4 Ra4+ 115. Kc3 Ra3+ 116. Kd4 Ra4+ 117. Ke3 Ra3 118. Rh8 Ke5 119. Rh5+ Kd6 120. Rg5 Rb3 121. Kd2 Rb8 122. Bf1 Re8 123. Kd3 Re5 124. Rg8 Rh5 125. Bg2 Kc5 126. Rf8 Rh6 127. Bf3 Rd6 128. Re8 Rc6 129. Ra8 Rb6 130. Rd8 Rd6 131. Rf8 Ra6 132. Rf5 Rd6 133. Kc3 Rd8 134. Rg5 Rd6 135. Rh5 Rd8 136. Rf5 Rd6 137. Rf8 Ra6 138. Re8 Rc6 139. Ra8 Rb6 140. Ra5+ Rb5 141. Ra1 Rb8 142. Rd1 Rd8 143. Rd2 Rd7 144. Bg2 Rd8 145. Kd3 Ra8 146. Ke3 Re8+ 147. Kd3 Ra8 148. Kc3 Rd8 149. Bf3 Rd7 150. Kd3 Ra7 151. Bg2 Ra8 152. Rc2+ Kd6 153. Rc3 Ra2 154. Bf3 Ra8 155. Rb3 Ra5 156. Ke3 Ke5 157. Rd3 Rb5 158. Kd2 Rc5 159. Bg2 Ra5 160. Bf3 Rc5 161. Bd1 Rc8 162. Bb3 Rc5 163. Rh3 Kf4 164. Kd3 Ke5 165. Rh5+ Kf4 166. Kd4 Rb5 167. Bxd5 Rb4+ 168. Bc4 Ra4 169. Rh7 Kg5 170. Rf7 Kg6 171. Rf1 Kg5 172. Kc5 Ra5+ 173. Kc6 Ra4 174. Bd5 Rf4 175. Re1 Rf6+ 176. Kc5 Rf5 177. Kd4 Kf6 178. Re6+ Kg5 179. Be4 Rf6 180. Re8 Kf4 181. Rh8 Rd6+ 182. Bd5 Rf6 183. Rh1 Kf5 184. Be4+ Ke6 185. Ra1 Kd6 186. Ra5 Re6 187. Bf5 Re1 188. Ra6+ Ke7 189. Be4 Rc1 190. Ke5 Rc5+ 191. Bd5 Rc7 192. Rg6 Rd7 193. Rh6 Kd8 194. Be6 Rd2 195. Rh7 Ke8 196. Kf6 Kd8 197. Ke5 Rd1 198. Bd5 Ke8 199. Kd6 Kf8 200. Rf7+ Ke8
    """  # this is just a stub; realistically make this a *very long* PGN

    game = chess.pgn.read_game(StringIO(pgn_text))
    board = game.board()

    total_moves = 0
    # replay the same game N times, to ensure runtime
    for _ in range(20):
        game = chess.pgn.read_game(StringIO(pgn_text))
        board = game.board()
        for move in game.mainline_moves():
            board.push(move)
            total_moves += 1
            # heavy queries
            board.is_check()
            board.legal_moves.count()
            for sq in chess.SQUARES:
                board.attackers(chess.WHITE, sq)
                board.attackers(chess.BLACK, sq)

if __name__ == "__main__":
    main()