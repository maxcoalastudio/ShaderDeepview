from Range import *
from collections import OrderedDict
class Deepview(types.KX_PythonComponent):
	# Put your arguments here of the format ("key", default_value).
	# These values are exposed to the UI.
	args = OrderedDict({
        ('fog_density', 0.05),
        ('fog_color', (0.7, 0.7, 0.8)),
        ('fog_start', 5.0),
		('radial_strength', 0.5),
        ('center_x', 0.5),
        ('center_y', 0.5),

		('focal_distance', 10.0), 	#Distancia focal onde os objetos estão nitidos
		('dof_intensity', 0.5), 	#Intensidade do desfoque
		('wide_size', 2.0), 		#tamanho da abertura(suavidade da transição) 
	})

	def awake(self, args):
		self.fog_density = args['fog_density']
		self.fog_color = args['fog_color']
		self.fog_start = args['fog_start']

		self.radial_strength = args['radial_strength']
		self.center_point = [args['center_x'], args['center_y']]
		
		self.focal_distance = args['focal_distance']
		self.dof_intensity = args['dof_intensity']
		self.wide_size = args['wide_size']

		self.fragment_shader = """
        uniform sampler2D bgl_DepthTexture;  	//textura do zbuffer
        uniform sampler2D bgl_RenderedTexture; 	//textura da camera

        uniform float fog_density;   			//intensidade da neblina
        uniform vec3 fog_color;					//cor da neblina
        uniform float fog_start;				//distancia inicial da neblina
        uniform float near;						//plano de corte próximo
        uniform float far;						//plano de corte distante
		uniform float radial_strength;			//intensidade do efeito radial
		uniform vec2 center_point;				//ponto central do efeito radial

		uniform float focal_distance;			// Distância focal (objetos nítidos)
        uniform float dof_intensity;			// Intensidade do desfoque
        uniform float wide_size;				// Tamanho da abertura

        float linearize_depth(float depth) {	//função para linearizar a profundidade, perfeito para efeitos POS-PROCESSAMENTO E PRECISÃO
            float z = depth * 2.0 - 1.0;
            return (2.0 * near * far) / (far + near - z * (far - near));
		}
		
		// Função para calcular o círculo de confusão (CoC)
        float calculate_coc(float depth, float focal_dist, float aperture) {
            // Calcula quanto o ponto está fora de foco
            float coc = abs(depth - focal_dist);
            // Aplica abertura para controlar a suavidade
            coc = coc / (focal_dist * aperture);
            // Limita e suaviza o resultado
            return clamp(coc, 0.0, 1.0);
        }

        // Função para amostrar com offset
        vec4 sample_with_offset(vec2 texcoord, vec2 offset) {
            return texture2D(bgl_RenderedTexture, texcoord + offset);
        }
        

        void main() {
            vec2 texcoord = gl_TexCoord[0].st;	//coordenadas das texturas que vao ser usadas
			//obter a profundidade
            float depth = texture2D(bgl_DepthTexture, texcoord).r; 	//valor atual de cada pixel de profundidade da coordenada na textura atual gerada pela camera
            float linear_depth = linearize_depth(depth);			//armazenando o valor linearizado do buffer atual
            
			// Calcular distância radial do centro e aplica o efeito a profundidade
    		vec2 center = center_point; // Normalmente [0.5, 0.5] para centro da tela
    		float radial_distance = distance(texcoord, center);

			// Aplicar função radial à profundidade
			float radial_effect = radial_distance * radial_strength;
			float modified_depth = linear_depth * (1.0 + radial_effect);

			// Calcular círculo de confusão para DOF
            float coc = calculate_coc(linear_depth, focal_distance, wide_size);
            float blur_amount = coc * dof_intensity;

			vec4 scene_color = texture2D(bgl_RenderedTexture, texcoord);   	//pegando a cor da cena

			// Aplicar desfoque baseado na distância focal
            if (blur_amount > 0.01) {
                // Kernel simples para desfoque (5 amostras)
                vec4 blur_color = vec4(0.0);
                float total_weight = 0.0;

				// Definir offsets relativos baseados na quantidade de blur
				vec2 offsets[9] = vec2[](
					vec2(-1.0, -1.0), vec2(0.0, -1.0), vec2(1.0, -1.0),
					vec2(-1.0, 0.0), vec2(0.0, 0.0), vec2(1.0, 0.0),
					vec2(-1.0, 1.0), vec2(0.0, 1.0), vec2(1.0, 1.0)
				);
				// Aplicar pesos do kernel (Gaussiano simples)
				float weights[9] = float[](
					0.0625, 0.125, 0.0625,
					0.125, 0.25, 0.125,
					0.0625, 0.125, 0.0625
				);
				// Amostrar texturas com desfoque
				for (int i = 0; i < 9; i++) {
					vec2 sample_offset = offsets[i] * blur_amount * 0.01;
					blur_color += sample_with_offset(texcoord, sample_offset) * weights[i];
					total_weight += weights[i];
				}
				
				scene_color = blur_color / total_weight;
			}

            //combinando os dois expoente  radial e linear
            float fog_factor = exp((-fog_density * max(0.0, linear_depth - fog_start)) + exp(-0.05 * modified_depth));
            fog_factor = clamp(fog_factor, 0.0, 1.0);

			//aplica efeito misturando a cor da neblina com a textura
            vec3 final_color = mix(fog_color, scene_color.rgb, fog_factor);	//misturando todos elementos

            gl_FragColor = vec4(final_color, scene_color.a);//aplcando a cor, e o alpha recebe o alpha da cena original
        }
        """
        
        # Aplicar como filtro de pós-processamento
		filter_manager = self.object.scene.filterManager	#pegando o gerenciador de filtros da Range
		self.fog_filter = filter_manager.addFilter(			#criando o shader de filtro
            0,												#posição do filtro, na layer 0
            logic.RAS_2DFILTER_CUSTOMFILTER,				#tipo de filtro
            self.fragment_shader							#código do shader
        )
		self.shader = self.fog_filter						#armazenando o shader do filtro em uma variavel
	def start(self, args):
        # Atualizar parâmetros em tempo real
		#usamos o setUniform para passar os parametros para dentro do shader, usamos o nome entre aspas para os shaders, e o outro para variaveis do bge ou python
		camera = self.object.scene.active_camera
		self.shader.setUniform1f("near", camera.near)					
		self.shader.setUniform1f("far", camera.far)
		self.shader.setUniform1f("fog_density", self.fog_density)
		self.shader.setUniform3f("fog_color", *self.fog_color)
		self.shader.setUniform1f("fog_start", self.fog_start)

		self.shader.setUniform1f("radial_strength", self.radial_strength)
		self.shader.setUniform2f("center_point", *self.center_point)

		self.shader.setUniform1f("focal_distance", self.focal_distance)
		self.shader.setUniform1f("dof_intensity", self.dof_intensity)
		self.shader.setUniform1f("wide_size", self.wide_size)
	
	def update(self):
		pass