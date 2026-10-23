from conmutador_automatico import Conmutador

def main():
    conmutador = Conmutador()
    try:
        while True:
            print("\n" + "="*100)
            pregunta = input("pregunta: ")
            if pregunta.lower().strip() == "salir":
                print("\nAplicación terminada...")
                break
            respuesta = conmutador(pregunta=pregunta)
            print(f"\nRespuesta: {respuesta}")
    finally:
        conmutador.close()

if __name__ == "__main__":
    main()